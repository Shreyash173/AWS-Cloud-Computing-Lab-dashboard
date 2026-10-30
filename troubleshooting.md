# Troubleshooting Guide — AWS Cloud Computing Lab #2

---

## Local Docker Issues

### Problem: `docker compose up` fails — port already in use

**Symptom**: `Error … address already in use` or `Bind for 0.0.0.0:5000 failed`

**Cause**: Another process is using port 5000.

**Fix**:
```powershell
# Find what is using port 5000
netstat -ano | findstr :5000

# Kill it by PID (replace 12345 with actual PID)
taskkill /PID 12345 /F

# Or change the port in docker-compose.yml
# ports:
#   - "5001:5000"   <-- use 5001 on your machine
```

---

### Problem: Dashboard shows "Redis Unavailable"

**Symptom**: The red "Redis Unavailable" status shows on the dashboard.

**Cause**: The frontend container cannot reach Redis.

**Diagnosis**:
```powershell
# Check both containers are running
docker compose ps

# Check the Redis container health
docker inspect lab2-redis --format "{{.State.Health.Status}}"

# Check frontend environment variables
docker exec lab2-frontend env | Select-String REDIS
```

**Fix**:
- Make sure `REDIS_HOST=redis` in `docker-compose.yml` (not `localhost`).
- Make sure both containers are on the same network (`lab2-network`).
- Restart:
  ```powershell
  docker compose down && docker compose up --build -d
  ```

---

### Problem: Docker build fails — `requirements.txt not found`

**Symptom**: `COPY failed: file not found in build context`

**Cause**: You are running `docker build` from the wrong directory.

**Fix**: Always build from the project root (where `Dockerfile` lives):
```powershell
cd "c:\Users\Shreyash\Downloads\cloud computing"
docker compose up --build -d
```

---

### Problem: Changes to Flask code are not reflected

**Symptom**: You edited `app.py` but the running app is unchanged.

**Fix**: Rebuild the image:
```powershell
docker compose up --build -d
```
Docker caches layers. The `--build` flag forces it to rebuild the image.

---

## ECR Push Issues

### Problem: `UnauthorizedException` when pushing to ECR

**Symptom**: `no basic auth credentials` or `authorization token has expired`

**Fix**: Re-authenticate Docker with ECR:
```powershell
$REGION  = aws configure get region
$ACCOUNT = aws sts get-caller-identity --query Account --output text
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
```

---

### Problem: `AccessDeniedException` — cannot create ECR repository

**Symptom**: `User ... is not authorized to perform: ecr:CreateRepository`

**Fix**: Ask your AWS administrator to add the `AmazonEC2ContainerRegistryPowerUser`
managed policy to your IAM user or role.

---

## Kubernetes / EKS Issues

### Problem: Pods stuck in `ImagePullBackOff`

**Symptom**: `kubectl get pods` shows `ImagePullBackOff` or `ErrImagePull`

**Cause**: Kubernetes cannot pull the image from ECR.

**Diagnosis**:
```powershell
kubectl describe pod <POD_NAME>
# Look for "Failed to pull image" in the Events section
```

**Fix**:
1. Check that the image URI in `k8s/deployment.yaml` is correct.
2. Ensure the EKS node role has `AmazonEC2ContainerRegistryReadOnly` policy.
3. Check the image exists in ECR:
   ```powershell
   aws ecr list-images --repository-name lab2-frontend
   ```

---

### Problem: Pod stuck in `CrashLoopBackOff`

**Symptom**: Pod starts but immediately crashes and keeps restarting.

**Diagnosis**:
```powershell
kubectl logs <POD_NAME>
kubectl logs <POD_NAME> --previous    # logs from the previous (crashed) instance
kubectl describe pod <POD_NAME>
```

**Common causes**:
- `REDIS_HOST` is wrong — check the environment variable matches the Redis Service name.
- Application code has a syntax error — check the logs for Python tracebacks.

---

### Problem: `kubectl get hpa` shows `<unknown>` for TARGETS

**Symptom**: `TARGETS: <unknown>/50%`

**Cause**: The `metrics-server` is not installed or not ready.

**Fix**:
```powershell
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Wait 1–2 minutes then check
kubectl get deployment metrics-server -n kube-system
kubectl top nodes
kubectl top pods
```

---

### Problem: LoadBalancer service shows `<pending>` for EXTERNAL-IP

**Symptom**: `kubectl get service lab2-frontend-service` shows `<pending>` for minutes.

**Cause**: EKS is provisioning the AWS Load Balancer — this normally takes 2–5 minutes.

**Fix**: Wait. If it is still pending after 10 minutes:
```powershell
kubectl describe service lab2-frontend-service
# Look at Events for error messages
```

Check that your EKS node role has permissions to create load balancers
(`elasticloadbalancing:*`).

---

### Problem: `kubectl apply` — `no matches for kind "HorizontalPodAutoscaler"`

**Symptom**: Error about unknown API version.

**Fix**: Check your cluster supports `autoscaling/v2`:
```powershell
kubectl api-versions | Select-String autoscaling
```

If only `autoscaling/v1` is available, edit `k8s/hpa.yaml` and change
`apiVersion: autoscaling/v2` to `apiVersion: autoscaling/v1`.

---

## PowerShell Script Issues

### Problem: `push-to-ecr.ps1` — execution policy error

**Symptom**: `cannot be loaded because running scripts is disabled on this system`

**Fix**:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\push-to-ecr.ps1
```

This only changes the policy for the current PowerShell session — safe for lab use.

---

## General Tips

```powershell
# See all running containers
docker ps -a

# See all K8s resources at once
kubectl get all

# Follow logs from all pods matching a label
kubectl logs -l app=lab2-frontend -f

# Restart a deployment (pulls a fresh pod)
kubectl rollout restart deployment lab2-frontend

# Check cluster node status
kubectl get nodes -o wide
```
