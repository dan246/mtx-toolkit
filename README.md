# MTX Toolkit - Stream Reliability Toolkit

MediaMTX 串流可靠性管理工具箱，提供企業級的串流監控、自動修復、配置管理與多節點管理功能。

## 功能特色

- **E2E 健康檢查** - 使用 ffprobe 實際拉流檢測，支援黑屏/凍結、FPS 掉落、延遲等問題偵測
- **自動修復** - 斷線分級重試 (exponential backoff + jitter)，自動重啟異常串流
- **Config-as-Code** - 類似 Terraform 的 plan/apply 工作流程，支援 diff、驗證、備份、回滾
- **Fleet 管理** - 多台 MediaMTX 節點統一管理，支援跨環境 (dev/staging/prod)
- **錄影管理** - 事件分段錄影、磁碟水位保護、自動清理與歸檔
- **中英文介面** - 支援繁體中文與英文切換

## 技術架構

| 元件 | 技術 |
|------|------|
| 後端 | Python + Flask |
| 前端 | React + TypeScript + Vite |
| 資料庫 | PostgreSQL |
| 快取/佇列 | Redis + Celery |
| 容器化 | Docker Compose |

## 系統需求

- Docker & Docker Compose
- 運行中的 MediaMTX 實例
- 建議 2GB+ RAM

## 快速開始

### 1. 複製專案

```bash
cd /home/ubuntu/mtx-toolkit
```

### 2. 設定環境變數

編輯 `docker-compose.yml`，修改 MediaMTX 連線資訊：

```yaml
environment:
  - MEDIAMTX_API_URL=http://host.docker.internal:9998  # MediaMTX API 位址
  - MEDIAMTX_RTSP_URL=rtsp://host.docker.internal:8555  # MediaMTX RTSP 位址
```

### 3. 啟動服務

```bash
docker compose up -d
```

### 4. 存取介面

- **前端 UI**: http://localhost:3001
- **後端 API**: http://localhost:5002

## 初次設定

### 新增 MediaMTX 節點

首次使用需要先註冊你的 MediaMTX 節點：

```bash
# 新增節點
curl -X POST http://localhost:5002/api/fleet/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "main-mediamtx",
    "api_url": "http://host.docker.internal:9998",
    "rtsp_url": "rtsp://host.docker.internal:8555",
    "environment": "production"
  }'

# 同步串流資料
curl -X POST http://localhost:5002/api/fleet/nodes/1/sync
```

或透過 UI 操作：
1. 進入 **Fleet 節點管理** 頁面
2. 點擊 **Sync All** 同步所有節點

## 功能使用說明

### Dashboard 儀表板

總覽所有串流狀態、活動告警、最近事件。

### Streams 串流管理

| 功能 | 說明 |
|------|------|
| Probe | 立即檢測串流健康狀態 (FPS、解析度、編碼等) |
| Remediate | 嘗試修復異常串流 |
| 篩選 | 依狀態篩選：Healthy / Degraded / Unhealthy / Unknown |

### Fleet 節點管理

| 功能 | 說明 |
|------|------|
| Sync | 同步單一節點的串流資料 |
| Sync All | 同步所有節點 |
| 環境篩選 | Production / Staging / Development |

### Config 配置管理

支援 YAML 格式的配置，採用 plan/apply 工作流程：

```yaml
# 範例配置
paths:
  cam1:
    source: rtsp://user:pass@192.168.1.100:554/stream
  cam2:
    source: rtsp://user:pass@192.168.1.101:554/stream
```

| 功能 | 說明 |
|------|------|
| Plan | 預覽變更內容，顯示 diff |
| Apply | 套用配置變更 |
| Rollback | 回滾至歷史快照 |

### Recordings 錄影管理

| 功能 | 說明 |
|------|------|
| Run Cleanup | 執行磁碟清理，刪除過期錄影 |
| Archive | 歸檔重要錄影，防止被自動清理 |

### Testing 測試工具

| 功能 | 說明 |
|------|------|
| Stream Probe | 輸入任意 URL 進行健康檢測 |
| Test Scenarios | 預設測試場景 (testsrc、黑屏、靜音等) |

## API 參考

### 串流 API

```bash
# 列出所有串流
GET /api/streams

# 探測串流
POST /api/health/probe/{stream_id}

# 修復串流
POST /api/streams/{stream_id}/remediate
```

### 節點 API

```bash
# 列出節點
GET /api/fleet/nodes

# 新增節點
POST /api/fleet/nodes

# 同步節點
POST /api/fleet/nodes/{node_id}/sync

# 同步所有節點
POST /api/fleet/sync-all
```

### 配置 API

```bash
# Plan 配置
POST /api/config/plan
Content-Type: application/json
{"config_yaml": "...", "node_id": 1}

# Apply 配置
POST /api/config/apply
Content-Type: application/json
{"config_yaml": "...", "node_id": 1}

# 列出快照
GET /api/config/snapshots

# 回滾配置
POST /api/config/rollback/{snapshot_id}
```

## 服務埠號

| 服務 | 埠號 |
|------|------|
| Frontend | 3001 |
| Backend API | 5002 |
| PostgreSQL | 15433 |
| Redis | 6380 |

## 常用指令

```bash
# 啟動所有服務
docker compose up -d

# 查看服務狀態
docker compose ps

# 查看日誌
docker compose logs -f backend
docker compose logs -f frontend

# 重建前端
docker compose build frontend && docker compose up -d frontend

# 重建後端
docker compose build backend && docker compose up -d backend celery-worker celery-beat

# 停止所有服務
docker compose down

# 完全清除 (包含資料庫)
docker compose down -v
```

## 目錄結構

```
mtx-toolkit/
├── backend/
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── models/       # 資料庫模型
│   │   ├── services/     # 業務邏輯
│   │   └── utils/        # 工具函數
│   ├── migrations/       # 資料庫遷移
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # React 元件
│   │   ├── pages/        # 頁面
│   │   ├── services/     # API 呼叫
│   │   ├── i18n/         # 多語系
│   │   └── types/        # TypeScript 型別
│   └── package.json
├── docker-compose.yml
└── README.md
```

## 疑難排解

### 串流列表為空

確認已新增節點並同步：
```bash
curl -X POST http://localhost:5002/api/fleet/nodes/1/sync
```

### 無法連線 MediaMTX

檢查 `docker-compose.yml` 中的 `MEDIAMTX_API_URL` 設定，確認：
- MediaMTX API 已啟用
- 防火牆允許連線
- 使用 `host.docker.internal` 存取主機服務

### 前端顯示錯誤

重建前端：
```bash
docker compose build frontend && docker compose up -d frontend
```

## License

MIT
