# AWS Monitoring — CloudWatch Setup Guide
# AWS Cloud Computing Lab #2

## Overview

This document explains how to configure Amazon CloudWatch to monitor the
Cloud Computing Lab #2 application running on Amazon EKS.

> **Cost Warning**: CloudWatch, Container Insights, and SNS all have associated
> costs. Stay within the [AWS Free Tier](https://aws.amazon.com/free/) limits
> where possible and delete resources when finished.

---

## 1. Amazon CloudWatch Container Insights

Container Insights collects CPU, memory, disk, and network metrics from your
EKS cluster and makes them available in CloudWatch.

### 1.1 Attach the Required IAM Policy

Your EKS node group's IAM role needs permission to publish metrics.

```bash
# Find your node group role name
aws eks describe-nodegroup \
  --cluster-name <YOUR_CLUSTER_NAME> \
  --nodegroup-name <YOUR_NODEGROUP_NAME> \
  --query "nodegroup.nodeRole" --output text

# Attach the CloudWatch agent policy
aws iam attach-role-policy \
  --role-name <NODE_ROLE_NAME> \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
```

### 1.2 Enable Container Insights on Your Cluster

```bash
aws eks update-addon \
  --cluster-name <YOUR_CLUSTER_NAME> \
  --addon-name amazon-cloudwatch-observability \
  --resolve-conflicts OVERWRITE
```

This installs the CloudWatch Agent and Fluent Bit as DaemonSets on your nodes.
After a minute or two, metrics will appear in CloudWatch under
**Container Insights → Performance Monitoring**.

---

## 2. CPU and Memory Monitoring

Once Container Insights is enabled, these metrics are available automatically:

| Metric Name | Description |
|---|---|
| `pod_cpu_utilization` | CPU % used by each pod |
| `pod_memory_utilization` | Memory % used by each pod |
| `pod_cpu_utilization_over_pod_limit` | CPU used vs the limit set in the manifest |
| `pod_memory_utilization_over_pod_limit` | Memory used vs the limit |
| `node_cpu_utilization` | CPU % at the node level |
| `node_memory_utilization` | Memory % at the node level |

> **Namespace**: all Container Insights metrics are published to
> `ContainerInsights` namespace in CloudWatch.

---

## 3. Creating a CloudWatch Dashboard

### Via the AWS Console

1. Open **CloudWatch** → **Dashboards** → **Create dashboard**.
2. Name it `Lab2-Dashboard` and click **Create dashboard**.
3. Click **Add widget** → **Line** → **Metrics**.
4. In the metric browser, navigate to:
   - `ContainerInsights` → `PodName` → `pod_cpu_utilization`
   - Filter by `ClusterName = <YOUR_CLUSTER_NAME>` and `Namespace = default`
5. Add a second widget for `pod_memory_utilization`.
6. Click **Save dashboard**.

### Via AWS CLI (example — add one metric widget)

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "Lab2-Dashboard" \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "x": 0, "y": 0, "width": 12, "height": 6,
        "properties": {
          "title": "Frontend Pod CPU Utilization",
          "metrics": [
            ["ContainerInsights", "pod_cpu_utilization",
             "PodName", "lab2-frontend",
             "ClusterName", "<YOUR_CLUSTER_NAME>",
             "Namespace", "default"]
          ],
          "period": 60,
          "stat": "Average",
          "view": "timeSeries"
        }
      }
    ]
  }'
```

---

## 4. CloudWatch Alarms

Alarms notify you (via SNS) when a metric crosses a threshold.

### 4.1 High CPU Alarm (triggers SNS email)

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "Lab2-HighCPU" \
  --alarm-description "Frontend pod CPU above 70% for 5 minutes" \
  --namespace "ContainerInsights" \
  --metric-name "pod_cpu_utilization" \
  --dimensions \
      Name=ClusterName,Value=<YOUR_CLUSTER_NAME> \
      Name=Namespace,Value=default \
      Name=PodName,Value=lab2-frontend \
  --statistic Average \
  --period 60 \
  --evaluation-periods 5 \
  --threshold 70 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:<REGION>:<ACCOUNT_ID>:Lab2-Alerts \
  --ok-actions    arn:aws:sns:<REGION>:<ACCOUNT_ID>:Lab2-Alerts
```

### 4.2 High Memory Alarm

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "Lab2-HighMemory" \
  --alarm-description "Frontend pod memory above 80%" \
  --namespace "ContainerInsights" \
  --metric-name "pod_memory_utilization" \
  --dimensions \
      Name=ClusterName,Value=<YOUR_CLUSTER_NAME> \
      Name=Namespace,Value=default \
      Name=PodName,Value=lab2-frontend \
  --statistic Average \
  --period 60 \
  --evaluation-periods 3 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:<REGION>:<ACCOUNT_ID>:Lab2-Alerts
```

---

## 5. Amazon SNS Email Notifications

### 5.1 Create an SNS Topic

```bash
aws sns create-topic --name Lab2-Alerts
# Note the TopicArn in the output — you will use it in alarm commands above.
```

### 5.2 Subscribe Your Email Address

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:<REGION>:<ACCOUNT_ID>:Lab2-Alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

**Check your email inbox** and click the confirmation link.
SNS will not deliver messages until the subscription is confirmed.

---

## 6. HTTP Request Count and P95 Latency (Application Instrumentation)

> **Important**: CloudWatch Container Insights does **NOT** automatically capture
> HTTP request counts or latency. These are application-level metrics that must
> be explicitly instrumented in the Flask code.

### Why manual instrumentation is needed

AWS ALB/ELB access logs can give you request counts, but P95 latency at the
application level requires the app itself to measure and report it.

### 6.1 Add Prometheus metrics to Flask (recommended approach)

Install the library:

```
prometheus-flask-exporter==0.23.1
```

Add three lines to `app/app.py`:

```python
from prometheus_flask_exporter import PrometheusMetrics

# After creating the Flask app:
metrics = PrometheusMetrics(app)
```

This automatically exposes a `/metrics` endpoint in Prometheus format, including:
- `flask_http_request_total` — HTTP request count by method, path, and status code
- `flask_http_request_duration_seconds` — histogram of request durations (P50, P95, P99)

### 6.2 Scrape metrics with CloudWatch Agent

Configure the CloudWatch Agent to scrape the `/metrics` endpoint and publish
the data to CloudWatch using EMF (Embedded Metric Format).

Add this section to the CloudWatch Agent config:

```json
{
  "logs": {
    "metrics_collected": {
      "prometheus": {
        "prometheus_config_path": "/etc/prometheusconfig/prometheus.yaml",
        "emf_processor": {
          "metric_declaration": [
            {
              "source_labels": ["job"],
              "label_matcher": "flask",
              "dimensions": [["Namespace","PodName"]],
              "metric_selectors": [
                "^flask_http_request_total$",
                "^flask_http_request_duration_seconds_bucket$"
              ]
            }
          ]
        }
      }
    }
  }
}
```

After this, you can create CloudWatch alarms on:
- `flask_http_request_total` — for request rate
- P95 latency derived from the histogram buckets

---

## 7. Cleanup

When you're done, delete monitoring resources to stop charges:

```bash
# Delete alarms
aws cloudwatch delete-alarms --alarm-names "Lab2-HighCPU" "Lab2-HighMemory"

# Delete dashboard
aws cloudwatch delete-dashboards --dashboard-names "Lab2-Dashboard"

# Delete SNS topic (first unsubscribe all)
aws sns delete-topic --topic-arn arn:aws:sns:<REGION>:<ACCOUNT_ID>:Lab2-Alerts
```
