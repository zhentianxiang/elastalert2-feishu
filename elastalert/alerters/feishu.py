#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书告警器，完美适配您的ES字段结构
支持文本和卡片两种消息格式，包含静默时段功能
"""

import json
import re
import requests
import os
import logging
import urllib.parse
from urllib.parse import quote
from datetime import datetime, timedelta
from elastalert.alerts import Alerter, DateTimeEncoder
from elastalert.util import elastalert_logger, EAException
from requests.exceptions import RequestException

class FeishuAlert(Alerter):
    """飞书告警器，专为您的ES字段结构优化"""

    required_options = frozenset(['feishu_webhook_url'])

    def __init__(self, rule):
        super(FeishuAlert, self).__init__(rule)
        
        elastalert_logger.info("初始化飞书告警器")
        
        # 从环境变量获取日志级别，默认为 DEBUG
        log_level = os.environ.get('ELASTALERT_LOG_LEVEL', 'DEBUG').upper()
        elastalert_logger.debug(f"获取到日志级别配置: {log_level}")
        
        # 设置日志级别
        if log_level == 'DEBUG':
            elastalert_logger.setLevel(logging.DEBUG)
        elif log_level == 'INFO':
            elastalert_logger.setLevel(logging.INFO)
        elif log_level == 'WARNING':
            elastalert_logger.setLevel(logging.WARNING)
        elif log_level == 'ERROR':
            elastalert_logger.setLevel(logging.ERROR)
        elif log_level == 'CRITICAL':
            elastalert_logger.setLevel(logging.CRITICAL)
        else:
            elastalert_logger.setLevel(logging.DEBUG)
            elastalert_logger.warning(f"未知的日志级别 '{log_level}'，将使用DEBUG级别")

        self.webhook_url = self.rule.get("feishu_webhook_url")
        self.alert_type = self.rule.get("feishu_alert_type", "card")  # 默认为卡片格式
        self.title = self.rule.get("feishu_title", "ElastAlert 告警通知")
        self.message_template = self.rule.get("feishu_message", "")
        self.skip = self.rule.get("feishu_skip", {})
        self.card_template = self.rule.get("feishu_card_template")
        self.kibana_base_url = self.rule.get("kibana_base_url", "").rstrip("/")

        elastalert_logger.debug(f"告警类型: {self.alert_type}")
        elastalert_logger.debug(f"标题: {self.title}")
        elastalert_logger.debug(f"静默时段配置: {self.skip}")

        if not self.webhook_url:
            error_msg = "feishu_webhook_url 是必须配置项"
            elastalert_logger.error(error_msg)
            raise EAException(error_msg)

    def get_info(self):
        info = {
            "type": "FeishuAlert",
            "alert_type": self.alert_type
        }
        elastalert_logger.debug(f"获取告警器信息: {info}")
        return info

    def is_in_silence_time(self):
        """检查当前是否在静默时段"""
        if "start" in self.skip and "end" in self.skip:
            now = datetime.now().strftime("%H:%M:%S")
            result = self.skip["start"] <= now <= self.skip["end"]
            elastalert_logger.debug(f"静默时段检查: 当前时间 {now}, 静默时段 {self.skip['start']}-{self.skip['end']}, 结果: {result}")
            return result
        elastalert_logger.debug("未配置静默时段或配置不完整")
        return False

    def render_template(self, template_str, match):
        """替换 {{字段}} 为 match 中的值，并清理掉控制字符"""
        elastalert_logger.debug("开始渲染模板")
        def replacer(m):
            key = m.group(1).strip()
            value = str(match.get(key, "N/A"))
            value = value.replace("\n", "").replace("\r", " ")
            elastalert_logger.debug(f"替换模板变量: {key} -> {value[:50]}...")  # 只记录前50个字符防止日志过长
            return value
    
        rendered = re.sub(r"{{\s*([^}]+)\s*}}", replacer, template_str)
        elastalert_logger.debug(f"渲染后模板内容: {rendered[:200]}...")  # 只记录前200个字符
        return rendered

    def create_text_body(self, match):
        """创建文本消息体"""
        elastalert_logger.info("创建文本消息体")
        try:
            # 转换 UTC 时间为本地时间并格式化
            if '@timestamp' in match:
                elastalert_logger.debug("发现@timestamp字段，进行时间转换")
                match['@timestamp_local'] = self.convert_utc_to_local(match['@timestamp'])
    
            formatted_message = self.message_template.format(
                alert_subject=match.get('alert_subject', '无标题'),
                timestamp=match.get('@timestamp_local', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
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
            
            elastalert_logger.debug(f"格式化后的消息内容: {formatted_message[:200]}...")
            
            text_body = {
                "msg_type": "text",
                "content": {
                    "text": f"{self.title}\n{formatted_message}"
                }
            }
            
            elastalert_logger.debug(f"生成的文本消息体: {json.dumps(text_body, ensure_ascii=False)[:300]}...")
            return text_body
    
        except KeyError as e:
            error_msg = f"消息格式化失败，缺少字段: {str(e)}。原始消息: {self.message_template}"
            elastalert_logger.error(error_msg)
            return {
                "msg_type": "text",
                "content": {
                    "text": error_msg
                }
            }

    def convert_utc_to_local(self, time_str):
        """时间格式化（如果已经是本地时间则只做格式化）"""
        elastalert_logger.debug(f"开始时间转换，原始时间: {time_str}")
        try:
            if not time_str:
                elastalert_logger.warning("时间字符串为空")
                return "N/A"

            # 如果是UTC时间（带Z结尾）
            if time_str.endswith('Z'):
                dt = datetime.fromisoformat(time_str[:-1] + '+00:00')
                local_time = (dt + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
                elastalert_logger.debug(f"UTC时间转换结果: {local_time}")
                return local_time
            # 如果已经是本地时间格式
            else:
                dt = datetime.fromisoformat(time_str.replace('Z', ''))
                local_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                elastalert_logger.debug(f"本地时间格式化结果: {local_time}")
                return local_time
        except Exception as e:
            elastalert_logger.warning(f"时间格式化失败: {str(e)}，返回原始时间: {time_str}")
            return time_str  # 返回原始时间

    def get_index_pattern_id(self, index_name):
        """根据实际索引名称自动推导 index pattern 并获取其 Kibana ID"""
        elastalert_logger.info(f"开始获取索引模式ID，索引名称: {index_name}")
        try:
            # 自动从索引中提取通配符 pattern
            index_pattern = re.sub(r'(-\d{4}(\.\d{2}){1,2})+$', '-*', index_name)
            elastalert_logger.debug(f"提取的 index pattern: {index_pattern}")
    
            es_host = self.rule.get("es_host", "http://localhost")
            es_port = self.rule.get("es_port", 9200)
            es_user = self.rule.get("es_user")
            es_password = self.rule.get("es_password")
            es_url = f"{es_host.rstrip('/')}:{es_port}"
            # 如果 es_host 没有协议，自动加上 http://
            if not es_url.startswith('http://') and not es_url.startswith('https://'):
                es_url = 'http://' + es_url
            
            elastalert_logger.debug(f"请求 Elasticsearch URL: {es_url}/.kibana/_search")

            query_body = {
                "size": 1000,
                "_source": ["index-pattern.title"],
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"type": "index-pattern"}}
                        ]
                    }
                }
            }
    
            req_kwargs = {
                "json": query_body,
                "headers": {"Content-Type": "application/json"},
                "timeout": 10
            }
            if es_user and es_password:
                req_kwargs["auth"] = (es_user, es_password)
                elastalert_logger.debug("使用 Basic Auth 连接 Kibana")
    
            resp = requests.post(f"{es_url}/.kibana/_search", **req_kwargs)
            resp.raise_for_status()
            results = resp.json()
    
            hits = results.get("hits", {}).get("hits", [])
            elastalert_logger.debug(f"获取到 index-pattern 数量: {len(hits)}")
    
            for hit in hits:
                source = hit.get("_source", {})
                title = source.get("index-pattern", {}).get("title")
                _id = hit.get("_id")
                elastalert_logger.debug(f"发现 index-pattern: title={title}, id={_id}")
                if title == index_pattern:
                    elastalert_logger.info(f"匹配到 index pattern: {index_pattern} → ID: {_id}")
                    return _id
    
            elastalert_logger.warning(f"未找到匹配的 index-pattern: {index_pattern}")
            return index_pattern
        except Exception as e:
            elastalert_logger.error(f"获取 index pattern ID 失败: {e}")
            return index_name

    def generate_kibana_link(self, match):
        """生成 Kibana 链接（适配索引模式问题）"""
        elastalert_logger.info("开始生成Kibana链接")
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
            
            elastalert_logger.debug(f"原始索引: {raw_index}, 命名空间: {ns}, Pod: {pod}, 时间戳: {log_timestamp}")
            
            if not all([raw_index, ns, pod]):
                warning_msg = f"缺少必要字段构建链接: index={raw_index}, ns={ns}, pod={pod}"
                elastalert_logger.warning(warning_msg)
                return warning_msg
    
            # 从 _index 构造 pattern
            index_pattern = re.sub(r'(-\d{4}(\.\d{2}){1,2})+$', '-*', raw_index)
            elastalert_logger.debug(f"生成的索引模式: {index_pattern}")

            # 获取 index-pattern 的真实 ID
            index_pattern_id = self.get_index_pattern_id(raw_index)
            elastalert_logger.debug(f"获取到的索引模式ID: {index_pattern_id}")
 
            # 构造基础查询条件
            kuery_parts = [
                f'kubernetes_namespace_name:"{ns}"',
                f'kubernetes_pod_name:"{pod}"'
            ]
            
            # 添加消息查询条件
            if raw_message:
                first_line = raw_message.split('\n')[0].strip()
                if first_line:
                    max_len = 100
                    trimmed_msg = first_line[:max_len]
            
                    # 自动补齐未截断的单词
                    if trimmed_msg and trimmed_msg[-1].isalnum():
                        extra = ''
                        for ch in first_line[max_len:]:
                            if ch.isalnum():
                                extra += ch
                            else:
                                break
                        trimmed_msg += extra
           
                    escaped_msg = trimmed_msg.replace('"', '\\"')
                    kuery_parts.append(f'message:"{escaped_msg}*"')
                    elastalert_logger.debug(f"添加消息查询条件: {escaped_msg}*")
    
            kuery_query = " and ".join(kuery_parts)
            # 对整个KQL查询进行URL编码
            kuery_query_encoded = urllib.parse.quote(kuery_query, safe='')
            elastalert_logger.debug(f"生成kibana的KQL查询: {kuery_query_encoded}")
    
            # 处理时间范围（使用日志时间±5分钟）
            if log_timestamp:
                try:
                    # 将日志时间转换为datetime对象（假设格式为ISO 8601）
                    if log_timestamp.endswith('Z'):
                        log_time = datetime.fromisoformat(log_timestamp[:-1] + '+00:00')
                    else:
                        log_time = datetime.fromisoformat(log_timestamp.replace('Z', ''))
                    
                    elastalert_logger.debug(f"解析后的日志时间(UTC): {log_time}")
                    
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
                    
                    elastalert_logger.debug(f"生成的时间范围: {time_range}")
                except Exception as e:
                    elastalert_logger.warning(f"解析日志时间失败，使用默认时间范围: {str(e)}")
                    time_range = "(from:now-15m,to:now)"
            else:
                elastalert_logger.debug("未找到日志时间戳，使用默认时间范围")
                time_range = "(from:now-15m,to:now)"
    
            # 构造完整 Discover URL
            url = (
                f"{base_url}#/discover?"
                f"_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:{time_range})&"
                f"_a=(columns:!(_source),index:'{index_pattern_id}',interval:auto,"
                f"query:(language:kuery,query:'{kuery_query_encoded}'),sort:!('@timestamp',desc))"
            )
            
            elastalert_logger.info(f"生成的 Kibana URL: {url[:200]}...")  # 只记录前200个字符
            return url
        except Exception as e:
            elastalert_logger.error(f"生成 Kibana URL 失败: {str(e)}", exc_info=True)
            return "Kibana 链接生成失败"

    def create_card_body(self, match):
        """从模板创建卡片消息体（已修复多行日志和特殊字符问题）"""
        elastalert_logger.info("开始创建卡片消息体")
        if not self.card_template:
            error_msg = "feishu_alert_type=card 时必须提供 feishu_card_template"
            elastalert_logger.error(error_msg)
            raise EAException(error_msg)
    
        try:
            # 转换时间格式
            if '@timestamp' in match:
                elastalert_logger.debug("发现@timestamp字段，进行时间转换")
                match['@timestamp_local'] = self.convert_utc_to_local(match['@timestamp'])

            # 生成 Kibana URL 并添加到 match 字典中
            match["kibana_url"] = self.generate_kibana_link(match)
            elastalert_logger.debug(f"生成的Kibana URL: {match['kibana_url'][:200]}...")
            
            # 1. 将模板转为JSON字符串（保留中文等非ASCII字符）
            template_str = json.dumps(self.card_template, ensure_ascii=False)
            elastalert_logger.debug(f"原始模板字符串: {template_str[:200]}...")
    
            # 2. 渲染模板变量并严格转义特殊字符
            def safe_render(m):
                key = m.group(1).strip()
                value = str(match.get(key, "N/A"))
                # 转义所有JSON特殊字符（包括换行、引号、制表符等）
                rendered = json.dumps(value, ensure_ascii=False)[1:-1]  # 去掉外层的双引号
                elastalert_logger.debug(f"安全渲染变量: {key} -> {rendered[:50]}...")
                return rendered
    
            rendered_template = re.sub(r"{{\s*([^}]+)\s*}}", safe_render, template_str)
            elastalert_logger.debug(f"渲染后模板内容: {rendered_template[:200]}...")
    
            # 3. 解析为JSON对象
            card_data = json.loads(rendered_template)
            elastalert_logger.debug("成功解析渲染后的模板为JSON")
    
            # 4. 处理elements中的动态内容（二次转义）
            for i, element in enumerate(card_data.get('card', {}).get('elements', [])):
                if 'text' in element and 'content' in element['text']:
                    content = element['text']['content']
                    if '{{' in content:  # 如果内容包含需要渲染的变量
                        rendered = re.sub(r"{{\s*([^}]+)\s*}}", safe_render, content)
                        element['text']['content'] = rendered
                        elastalert_logger.debug(f"处理元素 {i} 内容: {rendered[:100]}...")
    
            elastalert_logger.debug(f"最终卡片数据: {json.dumps(card_data, ensure_ascii=False)[:300]}...")
            return card_data
    
        except json.JSONDecodeError as e:
            # 记录渲染失败的模板内容（调试用）
            elastalert_logger.error(f"JSON解析失败，错误位置: {e.lineno}, {e.colno}")
            elastalert_logger.error(f"渲染后模板内容: {rendered_template[e.pos-50:e.pos+50]}")
            raise EAException(f"飞书卡片JSON解析失败: {str(e)}")
        except Exception as e:
            elastalert_logger.error(f"渲染飞书卡片失败: {str(e)}", exc_info=True)
            raise EAException(f"渲染飞书卡片失败: {str(e)}")

    def alert(self, matches):
        elastalert_logger.info(f"开始处理告警，匹配到 {len(matches)} 条记录")
        if self.is_in_silence_time():
            elastalert_logger.info("当前处于静默时段，跳过告警")
            return

        for i, match in enumerate(matches):
            elastalert_logger.info(f"处理第 {i+1}/{len(matches)} 条匹配记录")
            try:
                if self.alert_type == "card":
                    elastalert_logger.debug("使用卡片格式告警")
                    body = self.create_card_body(match)
                else:
                    elastalert_logger.debug("使用文本格式告警")
                    body = self.create_text_body(match)

                elastalert_logger.debug(f"准备发送的请求体: {json.dumps(body, ensure_ascii=False)[:300]}...")
                
                response = requests.post(
                    self.webhook_url,
                    data=json.dumps(body, cls=DateTimeEncoder),
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )

                elastalert_logger.debug(f"飞书接口响应状态码: {response.status_code}")
                elastalert_logger.debug(f"飞书接口响应内容: {response.text[:200]}...")

                if response.status_code != 200:
                    error_msg = f"飞书接口返回错误: {response.status_code}, {response.text}"
                    elastalert_logger.error(error_msg)
                    raise EAException(error_msg)

                elastalert_logger.info("飞书告警发送成功")
            except RequestException as e:
                error_msg = f"请求飞书接口失败: {str(e)}"
                elastalert_logger.error(error_msg, exc_info=True)
                raise EAException(error_msg)
            except Exception as e:
                elastalert_logger.error(f"处理飞书告警时出错: {str(e)}", exc_info=True)
                raise EAException(f"处理飞书告警时出错: {str(e)}")
