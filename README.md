# ElastAlert 2

ElastAlert 2 is a standalone software tool for alerting on anomalies, spikes, or other patterns of interest from data in [Elasticsearch][10] and [OpenSearch][9].

ElastAlert 2 is backwards compatible with the original [ElastAlert][0] rules.

![CI Workflow](https://github.com/jertel/elastalert/workflows/master_build_test/badge.svg)

## Docker and Kubernetes

ElastAlert 2 is well-suited to being run as a microservice, and is available
as an image on [Docker Hub][2] and on [GitHub Container Registry][11]. For more instructions on how to
configure and run ElastAlert 2 using Docker, see [here][8].

A [Helm chart][7] is also included for easy configuration as a Kubernetes deployment. 

## Documentation

Documentation, including an FAQ, for ElastAlert 2 can be found on [readthedocs.com][3]. This is the place to start if you're not familiar with ElastAlert 2 at all.

Elasticsearch 8 support is documented in the [FAQ][12].

The full list of platforms that ElastAlert 2 can fire alerts into can be found [in the documentation][4].

## Contributing

Please see our [contributing guidelines][6].

## Security

See our [security policy][13] for reporting urgent vulnerabilities.

## License

ElastAlert 2 is licensed under the [Apache License, Version 2.0][5].

[0]: https://github.com/yelp/elastalert
[1]: https://github.com/jertel/elastalert2/blob/master/examples/config.yaml.example
[2]: https://hub.docker.com/r/jertel/elastalert2
[3]: https://elastalert2.readthedocs.io/
[4]: https://elastalert2.readthedocs.io/en/latest/alerts.html#alert-types
[5]: https://www.apache.org/licenses/LICENSE-2.0
[6]: https://github.com/jertel/elastalert2/blob/master/CONTRIBUTING.md
[7]: https://github.com/jertel/elastalert2/tree/master/chart/elastalert2
[8]: https://elastalert2.readthedocs.io/en/latest/running_elastalert.html
[9]: https://opensearch.org/
[10]: https://github.com/elastic/elasticsearch
[11]: https://github.com/jertel/elastalert2/pkgs/container/elastalert2%2Felastalert2
[12]: https://elastalert2.readthedocs.io/en/latest/recipes/faq.html#does-elastalert-2-support-elasticsearch-8
[13]: https://github.com/jertel/elastalert2/blob/master/SECURITY.md

### 启动方式

```sh
$ kubectl apply -f .

$ kubectl get pods -n kube-logging -l app=elastalert
NAME                          READY   STATUS    RESTARTS   AGE
elastalert-754588569d-2gjn5   2/2     Running   0          10m

$ kubectl -n kube-logging logs --tail=100 -f elastalert-754588569d-2gjn5 elastalert-helloworld 
INFO:elastalert:开始处理告警，匹配到 1 条记录
INFO:elastalert:处理第 1/1 条匹配记录
INFO:elastalert:开始创建卡片消息体
INFO:elastalert:开始生成Kibana链接
INFO:elastalert:开始获取索引模式ID，索引名称: k8s-app-helloworld-2025.04.10
INFO:elastalert:匹配到 index pattern: k8s-app-helloworld-* → ID: index-pattern:389805b0-15e0-11f0-bd59-83accc289f92
INFO:elastalert:生成的 Kibana URL: http://k8s-kibana.linuxtian.com/app/kibana#/discover?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:'2025-04-10T10:35:05.000Z',to:'2025-04-10T10:45:05.000Z',display:'18:35:05 - 18:45:05...
INFO:elastalert:飞书告警发送成功
INFO:elastalert:开始处理告警，匹配到 1 条记录
INFO:elastalert:处理第 1/1 条匹配记录
INFO:elastalert:开始创建卡片消息体
INFO:elastalert:开始生成Kibana链接
INFO:elastalert:开始获取索引模式ID，索引名称: k8s-app-helloworld-2025.04.10
INFO:elastalert:匹配到 index pattern: k8s-app-helloworld-* → ID: index-pattern:389805b0-15e0-11f0-bd59-83accc289f92
INFO:elastalert:生成的 Kibana URL: http://k8s-kibana.linuxtian.com/app/kibana#/discover?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:'2025-04-10T10:36:45.000Z',to:'2025-04-10T10:46:45.000Z',display:'18:36:45 - 18:46:45...
INFO:elastalert:飞书告警发送成功
INFO:elastalert:Ignoring match for silenced rule k8s_error_log_helloworld.java.lang.RuntimeException: 权限不足
        at com.example.halloworld.controller.HalloController$ErrorLogWorker.run(HalloController.java:99)
        at java.lang.Thread.run(Thread.java:750)

INFO:elastalert:Ran k8s_error_log_helloworld from 2025-04-10 18:36 CST to 2025-04-10 18:41 CST: 18 query hits (14 already seen), 4 matches, 2 alerts sent
INFO:elastalert:k8s_error_log_helloworld range 300
INFO:elastalert:Background configuration change check run at 2025-04-10 18:42 CST
INFO:elastalert:Disabled rules are: []
INFO:elastalert:Sleeping for 59.999854 seconds
INFO:elastalert:Background alerts thread 0 pending alerts sent at 2025-04-10 18:42 CST
INFO:elastalert:Queried rule k8s_error_log_helloworld from 2025-04-10 18:37 CST to 2025-04-10 18:42 CST: 16 / 16 hits
```

