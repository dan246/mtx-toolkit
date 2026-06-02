<h1 align="center">MTX Toolkit</h1>

<p align="center">
  <strong>企業級 MediaMTX 串流可靠性管理平台</strong>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="#功能特色">功能</a> •
  <a href="#截圖">截圖</a> •
  <a href="#快速開始">快速開始</a> •
  <a href="#架構">架構</a> •
  <a href="#api-參考">API</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/react-18+-61DAFB.svg" alt="React">
  <img src="https://img.shields.io/badge/docker-ready-2496ED.svg" alt="Docker">
</p>

---

## 概述

MTX Toolkit 是一個專為 MediaMTX 設計的企業級串流可靠性管理平台。除了即時監控與多節點管理,它還加入了**串流可靠性層**——幀級活性偵測、協定感知復活、reader-preserving fallback、HLS 播放器看門狗、錄影管線監控——並由 5 級自動修復引擎驅動。整個 API 皆受 token 認證保護。支援同時監控**上千台攝影機**,並在約 10 秒內完成全面健康檢查。

## 功能特色

| 功能 | 說明 |
|------|------|
| **使用者認證** | Token 登入,保護所有變更/控制端點;首次啟動自動建立管理員 |
| **即時預覽** | 網格縮圖檢視,滑鼠懸停播放 HLS 預覽,點擊全螢幕播放 |
| **雙層健康檢查** | 快速檢查（API,每 10 秒）+ 深度檢查（ffprobe,每 5 分鐘） |
| **幀活性偵測** | 偵測「假活著」的串流:凍結 / 黑屏 / PTS 停滯 / 靜音（每 30 秒） |
| **自動修復** | 5 級分級重試（軟重置 → 協定復活 → 重啟 sidecar/path/server）含退避 + 抖動 |
| **協定感知復活** | RTSP / RTMP / WebRTC / HLS 策略,依 MediaMTX source type 自動偵測 |
| **Reader-Preserving Fallback** | 修復期間將失效來源切換為彩條 / 圖片 / 最後一幀,觀眾不斷線 |
| **HLS 播放器看門狗** | 前端停滯自動恢復（seek → 切換 level → 完整重載）並回報後端 |
| **錄影管線監控** | 追蹤每個啟用錄影串流的寫入延遲、segment 間隙、磁碟 IO |
| **即時監控** | 支援 1000+ 串流,毫秒級狀態更新 |
| **Fleet 管理** | 多節點統一管理,跨環境部署（dev/staging/prod） |
| **觀眾管理** | 即時觀眾連線狀態,依協定/節點篩選,踢出觀眾 |
| **IP 黑名單** | 封鎖濫用觀眾 IP(暫時或永久,可限定 path / node 範圍) |
| **Config-as-Code** | Terraform 風格的 plan/apply/rollback 工作流程 |
| **錄影管理** | 目錄掃描、線上播放、搜尋與分頁、自動清理與歸檔 |
| **整合測試** | 即時 ffmpeg 測試情境 + 真實的整合 / 壓力 / 故障復原測試（非模擬） |
| **事件管理** | 批次解決、清理舊事件、清除已解決告警 |
| **多語系** | 繁體中文 / English（所有 UI 文字、toast 與對話框） |

## 截圖

### 儀表板
即時監控所有串流狀態、健康分佈、活動告警與最近事件。包含事件管理按鈕，可一鍵解決所有告警、清除已解決事件或清理舊事件。

![Dashboard](docs/screenshots/dashboard.png)

### 即時預覽
所有串流的網格檢視，自動生成縮圖。滑鼠懸停播放即時 HLS 串流，點擊開啟全螢幕播放器（含音訊控制）。

![Preview](docs/screenshots/preview.png)

### 節點管理
多節點統一管理，顯示每個節點的串流健康狀況（健康/降級/不健康）。

![Fleet Management](docs/screenshots/fleet.png)

### 串流管理
完整的串流 CRUD 操作，支援狀態篩選、FPS/位元率監控、手動探測與修復。

![Streams](docs/screenshots/streams.png)

### 錄影管理
錄影檔案管理，支援目錄掃描、線上播放（TS 自動轉檔 MP4）、跨分頁搜尋、分頁瀏覽、磁碟使用量監控與自動清理。

![Recordings](docs/screenshots/recordings.png)

### 觀眾管理
即時監控所有 MediaMTX 節點的觀眾連線。顯示客戶端 IP、協定（RTSP/WebRTC/RTMP/SRT）、連線時長、傳輸資料量，並可踢出觀眾。

![Viewers](docs/screenshots/viewers.png)

## 健康檢查系統

### 串流狀態

| 狀態 | 顏色 | 說明 |
|------|:----:|------|
| **Healthy** | 🟢 | 串流正常，可播放 |
| **Degraded** | 🟡 | 連線中、監聽待機、或暫時不可用 |
| **Unhealthy** | 🔴 | 路徑不存在或完全離線 |
| **Unknown** | ⚪ | 尚未檢查 |

### 雙層檢查架構

```
┌─────────────────────────────────────────────────────────────┐
│                Quick Check - 主要監控                        │
│                      (每 10 秒)                              │
│  ┌─────────┐    ┌─────────────┐    ┌──────────────────┐    │
│  │ MediaMTX │───▶│  API Query  │───▶│ ready: true/false │    │
│  │   API    │    │ /v3/paths   │    │   狀態更新        │    │
│  └─────────┘    └─────────────┘    └──────────────────┘    │
│                    ⬇ 所有串流 ~0.2 秒                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Deep Check - 詳細診斷                         │
│                      (每 5 分鐘)                             │
│  ┌─────────┐    ┌─────────────┐    ┌──────────────────┐    │
│  │  RTSP   │───▶│   ffprobe   │───▶│ FPS, 解析度,      │    │
│  │ Stream  │    │  TCP Mode   │    │ 編碼, 位元率      │    │
│  └─────────┘    └─────────────┘    └──────────────────┘    │
│                    ⬇ 並行執行                               │
└─────────────────────────────────────────────────────────────┘
```

### 監控容量

| 串流數量 | 快速檢查時間 |
|:-------:|:-----------:|
| 200 | ~0.2 秒 |
| 1,000 | ~1 秒 |
| 5,000 | ~5 秒 |

## 串流可靠性層

串流可能「連著」卻其實壞了——凍結、黑屏或靜音。可靠性層會偵測這些狀況並自動恢復。

### 活性分類

| 分類 | 意義 |
|------|------|
| `live` | 幀正常前進,畫面與音訊正常 |
| `frozen` | 幀雜湊重複不變 |
| `black_screen` | 亮度低於門檻 |
| `stale` | 顯示時間戳（PTS）未前進 |
| `silent` | 音訊 RMS 低於門檻 |
| `unknown` | 尚未探測 |

### 5 級自動修復

活性觸發從第 0 級開始;健康檢查觸發從第 1 級開始。每級以指數退避 + 抖動重試後才升級。

```
0  SOFT_RESET          → 重拉來源 / 重置 path
1  PROTOCOL_REVIVAL    → 協定專屬復活（RTSP/RTMP/WebRTC/HLS）
2  RESTART_SIDECAR     → 重啟發布端 sidecar
3  RESTART_PATH        → 重建 MediaMTX path
4  RESTART_MEDIAMTX    → 重啟 MediaMTX 容器（最後手段）
```

修復期間,**reader-preserving fallback** 可將 path 來源切換為彩條 / 自訂圖片 / 最後一幀,讓已連線的觀眾在來源修復時不會斷線。內建**斷路器**(冷卻 + 近期失敗計數)防止修復風暴。

## 認證與安全

整個 API 都需要 bearer token,公開白名單除外(登入、容器健康檢查、瀏覽器播放回報遙測端點)。

- **首次啟動**會依 `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` 建立管理員(預設 `admin` / `admin`)。**請立即更改。**
- Token 經簽章(HMAC、有時效)。請設定強 `SECRET_KEY`——production/staging 下使用內建 dev 預設值會**拒絕啟動**,Docker Compose 若未設 `SECRET_KEY` 也會**直接失敗**。
- CORS 透過 `CORS_ORIGINS` 明確白名單(無萬用字元)。
- 串流 URL 內嵌的憑證(`rtsp://user:pass@…`)會在日誌中被遮蔽。

```bash
# 登入並取得 token
TOKEN=$(curl -s -X POST http://localhost:5002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .token)

# 用於任何受保護端點
curl http://localhost:5002/api/streams/ -H "Authorization: Bearer $TOKEN"

# 更改管理員密碼
curl -X POST http://localhost:5002/api/auth/change-password \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"current_password":"admin","new_password":"a-strong-new-password"}'
```

## 快速開始

### 系統需求

- Docker & Docker Compose
- 運行中的 MediaMTX 實例
- 2GB+ RAM

### 1. 設定密鑰

Docker Compose 要求必須設定 `SECRET_KEY`(否則 token 可被偽造)。複製範例並設定強值:

```bash
git clone <repo-url> mtx-toolkit
cd mtx-toolkit
cp .env.example .env
# 產生強密鑰:
echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> .env
# 可選:在 .env 設定 BOOTSTRAP_ADMIN_PASSWORD、CORS_ORIGINS 等
```

### 2. 啟動服務

```bash
docker compose up -d
```

### 3. 登入

開啟 http://localhost:3001,以管理員登入(預設 `admin` / `admin`,或你在 `.env` 設定的值)。請立即從 UI / API 更改密碼。

### 4. 存取介面

| 服務 | 網址 |
|------|------|
| **前端 UI** | http://localhost:3001 |
| **後端 API** | http://localhost:5002 |

### 5. 新增節點

透過 UI 或 API 新增你的 MediaMTX 節點：

```bash
curl -X POST http://localhost:5002/api/fleet/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "main-mediamtx",
    "api_url": "http://your-mediamtx:9998",
    "rtsp_url": "rtsp://your-mediamtx:8554",
    "environment": "production"
  }'
```

### 6. 同步串流

```bash
curl -X POST http://localhost:5002/api/fleet/sync-all
```

> 以下 `curl` 範例為求簡潔皆省略 `Authorization: Bearer $TOKEN` header——除公開白名單外,每個端點都需要它。

## 架構

```
┌────────────────────────────────────────────────────────────────┐
│                         MTX Toolkit                            │
├────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Frontend │  │ Backend  │  │  Celery  │  │  Celery  │      │
│  │  React   │  │  Flask   │  │  Worker  │  │   Beat   │      │
│  │  :3001   │  │  :5002   │  │          │  │          │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │             │
│       └─────────────┼─────────────┼─────────────┘             │
│                     │             │                           │
│              ┌──────┴──────┐ ┌────┴────┐                     │
│              │  PostgreSQL │ │  Redis  │                     │
│              │    :5432    │ │  :6379  │                     │
│              └─────────────┘ └─────────┘                     │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                      MediaMTX Nodes                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │   Node 1    │  │   Node 2    │  │   Node N    │           │
│  │ Production  │  │   Staging   │  │     Dev     │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└────────────────────────────────────────────────────────────────┘
```

## API 參考

> 除公開白名單(`/api/auth/login`、`/api/health/`、`/api/health/playback-report`)外,每個端點都需要 `Authorization: Bearer <token>`。

### 認證

```bash
# 登入 -> { token, user }
POST /api/auth/login        # { "username": "...", "password": "..." }

# 目前使用者
GET  /api/auth/me

# 更改密碼
POST /api/auth/change-password   # { "current_password": "...", "new_password": "..." }

# 登出(由 client 丟棄 token)
POST /api/auth/logout
```

### 健康檢查

```bash
# 快速檢查所有節點（毫秒級）
POST /api/health/quick-check

# 快速檢查單一節點
POST /api/health/quick-check/{node_id}

# 深度探測串流（ffprobe）
POST /api/health/streams/{stream_id}/probe
```

### 節點管理

```bash
# 列出節點
GET /api/fleet/nodes

# 新增節點
POST /api/fleet/nodes

# 同步節點串流
POST /api/fleet/nodes/{node_id}/sync

# 同步所有節點
POST /api/fleet/sync-all
```

### 串流管理

```bash
# 列出串流
GET /api/streams

# 修復串流(5 級分級重試)
POST /api/streams/{stream_id}/remediate

# 協定感知復活(第 0/1 級)
POST /api/streams/{stream_id}/soft-reset
POST /api/streams/{stream_id}/revive
```

### 串流可靠性

```bash
# 活性偵測 — 列出 / 探測 / 歷史
GET  /api/liveness/streams?classification=frozen
POST /api/liveness/streams/{stream_id}/probe
GET  /api/liveness/history/{stream_id}

# Reader-preserving fallback
PUT  /api/fallback/streams/{stream_id}        # { "fallback_type": "color_bars" }
POST /api/fallback/streams/{stream_id}/activate
POST /api/fallback/streams/{stream_id}/deactivate

# 錄影管線監控
GET  /api/pipeline/status
GET  /api/pipeline/gaps
POST /api/pipeline/streams/{stream_id}/check

# 客戶端播放遙測(公開 — 由 HLS 看門狗送出)
POST /api/health/playback-report
```

### IP 黑名單

```bash
GET    /api/blacklist            # 列出封鎖的 IP
POST   /api/blacklist            # { "ip_address": "1.2.3.4", "reason": "...", "duration": "1h" }
DELETE /api/blacklist/{id}       # 解除封鎖
```

### 整合測試

```bash
# 即時 ffmpeg 測試情境(伺服器自有,無 shell 注入)
GET  /api/testing/scenarios
POST /api/testing/scenarios/{id}/start    # testsrc | black | silence | lowfps
POST /api/testing/scenarios/{id}/stop

# 真實測試套件(無模擬結果)
POST /api/testing/suite/integration       # 探測每個串流,彙整通過/失敗
POST /api/testing/suite/stress            # { "url": "...", "concurrency": 5 }
POST /api/testing/suite/recovery          # 對串流軟重置並驗證恢復
```

### 錄影管理

```bash
# 列出錄影（支援搜尋與分頁）
GET /api/recordings?search=camera1&page=1&per_page=20

# 掃描本地錄影目錄
POST /api/recordings/scan
# Request: { "node_id": 1, "force_rescan": false }

# 串流播放錄影（自動轉檔供瀏覽器播放）
GET /api/recordings/{id}/stream

# 下載錄影
GET /api/recordings/{id}/download

# 執行清理
POST /api/recordings/retention/cleanup
```

### 事件管理

```bash
# 解決所有未解決事件
POST /api/dashboard/events/resolve-all

# 清除所有已解決事件
POST /api/dashboard/events/clear-resolved

# 清理舊事件（預設：7 天）
POST /api/dashboard/events/cleanup
# Request: { "days": 7, "resolved_only": false }
```

### 觀眾管理

```bash
# 列出所有觀眾連線（支援篩選與分頁）
GET /api/sessions?node_id=1&protocol=rtsp&page=1&per_page=50

# 取得觀眾統計摘要
GET /api/sessions/summary

# 依節點取得觀眾
GET /api/sessions/node/{node_id}

# 依串流路徑取得觀眾
GET /api/sessions/path/{stream_path}

# 踢出觀眾
POST /api/sessions/kick
# Request: { "node_id": 1, "session_id": "uuid", "protocol": "rtsp" }
```

### 配置管理

```bash
# Plan 配置變更
POST /api/config/plan

# Apply 配置
POST /api/config/apply

# 回滾配置
POST /api/config/rollback/{snapshot_id}
```

## 設定

### 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `SECRET_KEY` | *(dev 預設)* | Token 簽章金鑰。prod/staging 與 Docker Compose **必填**;否則 app/compose 拒絕啟動 |
| `JWT_SECRET_KEY` | 回退至 `SECRET_KEY` | 選用,認證 token 的獨立金鑰 |
| `JWT_ACCESS_TOKEN_EXPIRES_HOURS` | `12` | Token 有效時數 |
| `AUTH_ENABLED` | `true` | 對受保護端點強制認證(測試時關閉) |
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` | 初始管理員帳號(首次啟動建立) |
| `BOOTSTRAP_ADMIN_PASSWORD` | `admin` | 初始管理員密碼——**請立即更改** |
| `CORS_ORIGINS` | `localhost:3000,3001` | 逗號分隔白名單。prod/staging **必填**(無萬用字元) |
| `LOG_LEVEL` | `INFO` | 日誌等級(structlog) |
| `LOG_JSON` | `true`(prod)/ `false`(dev) | JSON 或人類可讀日誌 |
| `MEDIAMTX_API_URL` | `http://localhost:9998` | MediaMTX API 位址 |
| `MEDIAMTX_RTSP_URL` | `rtsp://localhost:8554` | MediaMTX RTSP 位址 |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL 連線字串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 連線字串 |

### Docker Compose

編輯 `docker-compose.yml` 修改連線設定：

```yaml
environment:
  - MEDIAMTX_API_URL=http://host.docker.internal:9998
  - MEDIAMTX_RTSP_URL=rtsp://host.docker.internal:8554
```

## 服務埠號

| 服務 | 埠號 |
|------|:----:|
| Frontend | 3001 |
| Backend API | 5002 |
| PostgreSQL | 15433 |
| Redis | 6380 |

## 常用指令

```bash
# 啟動服務
docker compose up -d

# 查看日誌
docker compose logs -f backend

# 重建前端
docker compose build frontend && docker compose up -d frontend

# 重建後端
docker compose build backend && docker compose up -d backend celery-worker celery-beat

# 停止服務
docker compose down

# 完全清除（含資料庫）
docker compose down -v
```

## 疑難排解

### 串流全部顯示不健康

確認節點的 RTSP URL 設定正確：

```bash
# 檢查節點設定
curl http://localhost:5002/api/fleet/nodes | jq '.nodes[] | {name, rtsp_url}'

# 更新 RTSP URL
curl -X PUT http://localhost:5002/api/fleet/nodes/1 \
  -H "Content-Type: application/json" \
  -d '{"rtsp_url": "rtsp://your-mediamtx:8554"}'
```

### 健康檢查超時

Celery 任務已優化為並行執行，如仍有問題：

```bash
# 重啟 Celery
docker compose restart celery-worker celery-beat
```

### 前端顯示舊版本

```bash
# 重建並重啟前端
docker compose build frontend && docker compose up -d frontend

# 清除瀏覽器快取 (Ctrl+Shift+R)
```

### `docker compose up` 出現 `SECRET_KEY is required`

Compose 在沒有簽章金鑰時會拒絕啟動(否則 token 可被偽造)。請建立 `.env` 並設定強 `SECRET_KEY`(見[快速開始](#1-設定密鑰))。

### 忘記管理員密碼

直接在資料庫重設:

```bash
docker compose exec backend python3 -c "from app import create_app,db; from app.models import User; \
app=create_app(); ctx=app.app_context(); ctx.push(); \
u=User.query.filter_by(username='admin').first(); u.set_password('new-password'); db.session.commit(); print('reset')"
```

## 升級既有部署

新資料表(`users`、可靠性層資料表)會由 `db.create_all()` 自動建立。既有資料表要新增**欄位**時,請套用 `backend/migrations/` 中的 SQL 腳本(例如 `add_users_table.sql`、`add_reliability_layer_columns.sql`):

```bash
docker compose exec postgres psql -U mtx -d mtx_toolkit -f /path/to/migration.sql
```

## 授權

MIT License
