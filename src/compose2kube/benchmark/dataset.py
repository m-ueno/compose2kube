# pod controller
input3 = """
services:
  db:
    image: postgres:13.9-bullseye
    restart: always
    environment:
      POSTGRES_PASSWORD: postgres
    expose:
      - "5432"
    volumes:
      - db_data:/var/lib/postgresql/data
  bff:
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/db
      - DATASET_SELECT_MODE=${DATASET_SELECT_MODE:?err}
      - UPLOAD_DIR=/user_experiment
    env_file:
      - .env
    image: ml-webapp-api
    restart: always
    ports:
      - "10999"
    volumes:
      - type: volume
        source: user_experiment
        target: /user_experiment
volumes:
  db_data:
"""

output3 = """
apiVersion: v1
kind: PersistentVolume
metadata:
  name: db-data-pv
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /var/lib/postgresql/data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: db-data-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: "db"
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: db
          image: postgres:13.9-bullseye
          env:
            - name: POSTGRES_PASSWORD
              value: "postgres"
          ports:
            - containerPort: 5432
          volumeMounts:
            - mountPath: /var/lib/postgresql/data
              name: db-data
  volumeClaimTemplates:
    - metadata:
        name: db-data
      spec:
        accessModes: [ "ReadWriteOnce" ]
        resources:
          requests:
            storage: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: db
spec:
  ports:
    - port: 5432
  selector:
    app: db
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bff
spec:
  replicas: 1
  selector:
    matchLabels:
      app: bff
  template:
    metadata:
      labels:
        app: bff
    spec:
      containers:
        - name: bff
          image: ml-webapp-api
          env:
            - name: DATABASE_URL
              value: "postgresql://postgres:postgres@db:5432/db"
            - name: DATASET_SELECT_MODE
              valueFrom:
                configMapKeyRef:
                  name: bff-config
                  key: DATASET_SELECT_MODE
            - name: UPLOAD_DIR
              value: "/user_experiment"
          ports:
            - containerPort: 10999
          volumeMounts:
            - mountPath: /user_experiment
              name: user-experiment
      volumes:
        - name: user-experiment
          emptyDir: {} 
---
apiVersion: v1
kind: Service
metadata:
  name: bff
spec:
  ports:
    - port: 10999
  selector:
    app: bff
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: bff-config
data:
  DATASET_SELECT_MODE: "your_value_here"
"""

# 環境変数そのまま
input4 = """
services:
  web:
    image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
    container_name: rule-editor
    # user: '${UID}:${GID}'
    restart: always
    environment:
      - http_proxy=$IMAGE_PROXY
      - HTTP_PROXY=$IMAGE_PROXY
      - https_proxy=$IMAGE_PROXY
      - HTTPS_PROXY=$IMAGE_PROXY
      - TZ=Asia/Tokyo
    ports:
      - $IMAGE_PORT:10081
    command: ["sh", "/workspace/analyzer-web/compose_entrypoint.sh"]
"""

output4 = """
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  ports:
    - protocol: TCP
      port: 10081
      targetPort: 10081
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: rule-editor
          image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
          env:
            - name: http_proxy
              value: $IMAGE_PROXY
            - name: HTTP_PROXY
              value: $IMAGE_PROXY
            - name: https_proxy
              value: $IMAGE_PROXY
            - name: HTTPS_PROXY
              value: $IMAGE_PROXY
            - name: TZ
              value: Asia/Tokyo
          ports:
            - containerPort: 10081
          command: ["sh", "/workspace/analyzer-web/compose_entrypoint.sh"]
"""
# Uncomment the following lines if you want to set the user
# securityContext:
#   runAsUser: ${UID}
#   runAsGroup: ${GID}

input5 = """services:
  act-sdk_exec:
    image: ${REGISTRY}/${REPOSITORY}/${MAIN_EXEC_IMAGE}
    tty: true
    restart: always
    ports:
      - "${GUI_FWD_PORT}:8002" # serverアプリとの通信
      - "${WSS_FWD_PORT}:5003" # Websocketとの通信
    depends_on:
      - act-sdk_app
    environment:
      PYTHONPATH: /workspace/app-base/src:/workspace
    volumes:
      - workspace_app:/workspace/app
      - ./log:/workspace/app/exec/log
      - ./app_container/src:/workspace/app/src
      - ./app_container/configs:/workspace/app/exec/configs
      - ./add_components/websocket_sv:/workspace/app-base/src/app_base/parts/websocket_sv
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined
    entrypoint: "/bin/sh -c ' cd /workspace/app/src && python3 SampleApp.py '"
volumes:
  workspace_app:
"""

output5 = """
apiVersion: v1
kind: Service
metadata:
  name: act-sdk-exec
spec:
  ports:
    - protocol: TCP
      port: 8002
      targetPort: 8002
    - protocol: TCP
      port: 5003
      targetPort: 5003
  selector:
    app: act-sdk-exec
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: act-sdk-exec
spec:
  replicas: 1
  selector:
    matchLabels:
      app: act-sdk-exec
  template:
    metadata:
      labels:
        app: act-sdk-exec
    spec:
      containers:
        - name: act-sdk-exec
          image: ${REGISTRY}/${REPOSITORY}/${MAIN_EXEC_IMAGE}
          tty: true
          env:
            - name: PYTHONPATH
              value: /workspace/app-base/src:/workspace
          ports:
            - containerPort: 8002
            - containerPort: 5003
          volumeMounts:
            - name: workspace-app
              mountPath: /workspace/app
            - name: log
              mountPath: /workspace/app/exec/log
            - name: src
              mountPath: /workspace/app/src
            - name: configs
              mountPath: /workspace/app/exec/configs
            - name: websocket-sv
              mountPath: /workspace/app-base/src/app_base/parts/websocket_sv
          securityContext:
            capabilities:
              add: ["SYS_ADMIN"]
            seccompProfile:
              type: Unconfined
          command: ["/bin/sh", "-c", "cd /workspace/app/src && python3 SampleApp.py"]
      volumes:
        - name: workspace-app
          persistentVolumeClaim:
            claimName: workspace-app-pvc
        - name: log
          hostPath:
            path: /absolute/path/to/log
        - name: src
          hostPath:
            path: /absolute/path/to/app_container/src
        - name: configs
          hostPath:
            path: /absolute/path/to/app_container/configs
        - name: websocket-sv
          hostPath:
            path: /absolute/path/to/add_components/websocket_sv
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workspace-app-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
"""

# コメントも変換
#
# input9 = input4
input9 = """
services:
  ad-generation:
    image: ad-generation:v1
    restart: always
    ports:
      - 80:5306
    environment:
      - TZ=Asia/Tokyo
      - NVIDIA_VISIBLE_DEVICES=all
    command: /app/start.sh
    # user: '${UID}:${GID}'
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]
"""
output9 = """
apiVersion: v1
kind: Service
metadata:
  name: ad-generation
spec:
  ports:
    - protocol: TCP
      port: 5306
      targetPort: 5306
  selector:
    app: ad-generation
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad-generation
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ad-generation
  template:
    metadata:
      labels:
        app: ad-generation
    spec:
      containers:
        - name: ad-generation
          image: ad-generation:v1
          env:
            - name: TZ
              value: Asia/Tokyo
            - name: NVIDIA_VISIBLE_DEVICES
              value: all
          ports:
            - containerPort: 5306
          command: ["/app/start.sh"]
          resources:
            limits:
              nvidia.com/gpu: 1
          # Uncomment the following lines if you want to set the user
          # securityContext:
          #   runAsUser: ${UID}
          #   runAsGroup: ${GID}
"""

input12 = """
services:
  notebook:
    ports:
      - "8888"
    image: ml-webapp-runner
    restart: always
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "wget -O - http://127.0.0.1:8888/jupyter/lab || exit 1"
        ]
      start_period: "10s"
      retries: 3
      timeout: "5s"
      interval: "30s"
"""

output12 = """
apiVersion: v1
kind: Service
metadata:
  name: notebook
spec:
  ports:
    - protocol: TCP
      port: 8888
      targetPort: 8888
  selector:
    app: notebook
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notebook
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notebook
  template:
    metadata:
      labels:
        app: notebook
    spec:
      containers:
        - name: notebook
          image: ml-webapp-runner
          ports:
            - containerPort: 8888
          livenessProbe:
            httpGet:
              path: /jupyter/lab
              port: 8888
            initialDelaySeconds: 10
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          restartPolicy: Always
"""
