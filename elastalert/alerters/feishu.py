#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书告警器，完美适配您的ES字段结构
支持文本和卡片两种消息格式，包含静默时段功能
支持飞书卡片消息点击跳转kibana链接页面
"""

import json
import re
import requests
from datetime import datetime, timedelta
from elastalert.alerts import Alerter, DateTimeEncoder
from elastalert.util import elastalert_logger, EAException
from requests.exceptions import RequestException

class FeishuAlert(Alerter):
    """飞书告警器，专为您的ES字段结构优化"""

    required_options = frozenset(['feishu_webhook_url'])

    def __init__(self, rule):
        super(FeishuAlert, self).__init__(rule)
        self.webhook_url = self.rule.get("feishu_webhook_url")
        self.alert_type = self.rule.get("feishu_alert_type", "card")  # 默认为卡片格式
        self.title = self.rule.get("feishu_title", "ElastAlert 告警通知")
        self.message_template = self.rule.get("feishu_message", "")
        self.skip = self.rule.get("feishu_skip", {})
        self.card_template = self.rule.get("feishu_card_template")
        self.kibana_base_url = self.rule.get("kibana_base_url", "").rstrip("/")

        if not self.webhook_url:
            raise EAException("feishu_webhook_url 是必须配置项")

    def get_info(self):
        return {
            "type": "FeishuAlert",
            "alert_type": self.alert_type
        }

    def is_in_silence_time(self):
        """检查当前是否在静默时段"""
        if "start" in self.skip and "end" in self.skip:
            now = datetime.now().strftime("%H:%M:%S")
            return self.skip["start"] <= now <= self.skip["end"]
        return False

    def render_template(self, template_str, match):
        """替换 {{字段}} 为 match 中的值，并清理掉控制字符"""
        def replacer(m):
            key = m.group(1).strip()
            # 获取字段值并转为字符串
            value = str(match.get(key, "N/A"))
            # 去除换行符和回车符
            value = value.replace("\n", " ").replace("\r", " ")
            return value
    
        return re.sub(r"{{\s*([^}]+)\s*}}", replacer, template_str)

    def create_text_body(self, match):
        """创建文本消息体"""
        try:
            # 转换 UTC 时间为本地时间并格式化
            if '@timestamp' in match:
                match['@timestamp_local'] = self.convert_utc_to_local(match['@timestamp'])
    
            formatted_message = self.message_template.format(
                alert_subject=match.get('alert_subject', '无标题'),
                timestamp=match.get('@timestamp_local', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),  # 使用本地时间
                message=match.get('message', '无详细消息'),
                num_hits=match.get('num_hits', 'N/A'),
                num_matches=match.get('num_matches', 'N/A'),
                kubernetes_host=match.get('kubernetes_host', 'N/A'),
                kubernetes_namespace_name=match.get('kubernetes_namespace_name', 'N/A'),
                kubernetes_pod_name=match.get('kubernetes_pod_name', 'N/A'),
                kubernetes_container_image=match.get('kubernetes_container_image', 'N/A'),
                kubernetes_container_name=match.get('kubernetes_container_name', 'N/A'),
                stream=match.get('stream', 'N/A'),
                index=match.get('_index', 'N/A')
            )
        except KeyError as e:
            formatted_message = f"消息格式化失败，缺少字段: {str(e)}。原始消息: {self.message_template}"
    
        return {
            "msg_type": "text",
            "content": {
                "text": f"{self.title}\n{formatted_message}"
            }
        }

    def convert_utc_to_local(self, time_str):
        """时间格式化（如果已经是本地时间则只做格式化）"""
        try:
            if not time_str:
                return "N/A"

            # 如果是UTC时间（带Z结尾）
            if time_str.endswith('Z'):
                dt = datetime.fromisoformat(time_str[:-1] + '+00:00')
                return (dt + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            # 如果已经是本地时间格式
            else:
                dt = datetime.fromisoformat(time_str.replace('Z', ''))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            elastalert_logger.warning("时间格式化失败: %s", str(e))
            return time_str  # 返回原始时间

    def generate_kibana_link(self, match):
        """生成 Kibana 链接（适配索引模式问题）"""
        try:
            base_url = self.kibana_base_url
            if not base_url:
                elastalert_logger.warning("未配置 Kibana 链接")
                return "未配置 Kibana 链接"
    
            raw_index = match.get('_index', '')
            ns = match.get('kubernetes_namespace_name')
            pod = match.get('kubernetes_pod_name')
            raw_message = match.get('message', '')
            log_timestamp = match.get('@timestamp')  # 获取日志时间戳
            
            if not all([raw_index, ns, pod]):
                elastalert_logger.warning("缺少必要字段构建链接: index=%s, ns=%s, pod=%s", raw_index, ns, pod)
                return "缺少必要字段构建链接"
    
            # 处理索引名称 - 使用带连字符的通配符形式
            if '-' in raw_index and not raw_index.endswith('*'):
                parts = raw_index.split('-')
                if len(parts) > 1:
                    index_pattern = '-'.join(parts[:-1]) + '-*'
                else:
                    index_pattern = raw_index + '*'
            else:
                index_pattern = raw_index
    
            # 构造基础查询条件
            kuery_parts = [
                f'kubernetes_namespace_name:"{ns}"',
                f'kubernetes_pod_name:"{pod}"'
            ]
            
            # 添加消息查询条件
            if raw_message:
                first_line = raw_message.split('\n')[0].strip()
                if first_line:
                    escaped_msg = first_line.replace('"', '\\"')[:100]
                    kuery_parts.append(f'message:"{escaped_msg}*"')
    
            kuery_query = " and ".join(kuery_parts)
    
            # 处理时间范围（使用日志时间±5分钟）
            if log_timestamp:
                try:
                    # 将日志时间转换为datetime对象（假设格式为ISO 8601）
                    if log_timestamp.endswith('Z'):
                        log_time = datetime.fromisoformat(log_timestamp[:-1] + '+00:00')
                    else:
                        log_time = datetime.fromisoformat(log_timestamp.replace('Z', ''))
                    
                    # 转换为UTC时间
                    from_time_utc = (log_time - timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    to_time_utc = (log_time + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    
                    # 同时添加本地时间参数（解决Kibana界面显示问题）
                    from_time_local = (log_time - timedelta(minutes=5)) + timedelta(hours=8)
                    to_time_local = (log_time + timedelta(minutes=5)) + timedelta(hours=8)
                    
                    time_range = (
                        f"(from:'{from_time_utc}',to:'{to_time_utc}',"
                        f"display:'{from_time_local.strftime('%H:%M:%S')} - {to_time_local.strftime('%H:%M:%S')}')"
                    )
                except Exception as e:
                    elastalert_logger.warning("解析日志时间失败，使用默认时间范围: %s", str(e))
                    time_range = "(from:now-15m,to:now)"
            else:
                time_range = "(from:now-15m,to:now)"
    
            # 构造完整 Discover URL
            url = (
                f"{base_url}#/discover?"
                f"_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:{time_range})&"
                f"_a=(columns:!(_source),index:'{index_pattern}',interval:auto,"
                f"query:(language:kuery,query:'{kuery_query}'),sort:!('@timestamp',desc))"
            )
            
            elastalert_logger.info("生成的 Kibana URL: %s", url)
            return url
        except Exception as e:
            elastalert_logger.error("生成 Kibana URL 失败: %s", str(e))
            return "Kibana 链接生成失败"

    def create_card_body(self, match):
        """从模板创建卡片消息体（已修复多行日志和特殊字符问题）"""
        if not self.card_template:
            raise EAException("feishu_alert_type=card 时必须提供 feishu_card_template")
    
        try:
            # 转换时间格式
            if '@timestamp' in match:
              match['@timestamp_local'] = self.convert_utc_to_local(match['@timestamp'])

            # 生成 Kibana URL 并添加到 match 字典中
            match["kibana_url"] = self.generate_kibana_link(match)
            
            # 1. 将模板转为JSON字符串（保留中文等非ASCII字符）
            template_str = json.dumps(self.card_template, ensure_ascii=False)
    
            # 2. 渲染模板变量并严格转义特殊字符
            def safe_render(m):
                key = m.group(1).strip()
                value = str(match.get(key, "N/A"))
                # 转义所有JSON特殊字符（包括换行、引号、制表符等）
                return json.dumps(value, ensure_ascii=False)[1:-1]  # 去掉外层的双引号
    
            rendered_template = re.sub(r"{{\s*([^}]+)\s*}}", safe_render, template_str)
    
            # 3. 解析为JSON对象
            card_data = json.loads(rendered_template)
    
            # 4. 处理elements中的动态内容（二次转义）
            for element in card_data.get('card', {}).get('elements', []):
                if 'text' in element and 'content' in element['text']:
                    content = element['text']['content']
                    if '{{' in content:  # 如果内容包含需要渲染的变量
                        rendered = re.sub(r"{{\s*([^}]+)\s*}}", safe_render, content)
                        element['text']['content'] = rendered
    
            return card_data
    
        except json.JSONDecodeError as e:
            # 记录渲染失败的模板内容（调试用）
            elastalert_logger.error("JSON解析失败，渲染后模板内容: %s", rendered_template)
            raise EAException(f"飞书卡片JSON解析失败: {str(e)}")
        except Exception as e:
            raise EAException(f"渲染飞书卡片失败: {str(e)}")

    def alert(self, matches):
        if self.is_in_silence_time():
            elastalert_logger.info("当前处于静默时段，跳过告警")
            return

        for match in matches:
            try:
                if self.alert_type == "card":
                    body = self.create_card_body(match)
                else:
                    body = self.create_text_body(match)

                response = requests.post(
                    self.webhook_url,
                    data=json.dumps(body, cls=DateTimeEncoder),
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )

                if response.status_code != 200:
                    raise EAException(f"飞书接口返回错误: {response.status_code}, {response.text}")

                elastalert_logger.info("飞书告警发送成功")
            except RequestException as e:
                raise EAException(f"请求飞书接口失败: {str(e)}")
            except Exception as e:
                elastalert_logger.exception("处理飞书告警时出错: %s", str(e))
                raise EAException(f"处理飞书告警时出错: {str(e)}")
