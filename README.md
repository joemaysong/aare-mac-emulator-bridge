# AARE Mac Emulator Bridge

在 Apple Silicon Mac 上執行 **Android 15 模擬器 + AARE**，先驗證本機畫面、聲音與觸控，再提供獨立的實驗性 Mac 藍牙／Wi-Fi 投影橋接。

**AARE 原作者是 [prototux](https://github.com/prototux)，原始專案為 [prototux/AARE](https://github.com/prototux/AARE)。** Android Auto 協定、Android app 與桌面接收端來自 AARE；本專案新增 Mac 重建流程、模擬器編碼器修補與傳輸整合。上游使用 GPL-3.0，完整引用與改動界線請見 [NOTICE.md](NOTICE.md)、[LICENSE](LICENSE)。

> **目前可以重建並測試 Mac 本機環境；Mac → EV6 的實際無線投影仍未驗證成功。** 本機模擬測試通過，不代表車機接受憑證、手機角色或 AAP 連線。本專案不包含車機刷機、APK 安裝到車機、AP 強制啟動、車控 API 或車機修補。

## 這份 repository 包含什麼

- 官方 AARE v1.1.1 與指定原始碼 commit 的 SHA-256 鎖定下載／重建配方。
- 專用 `AARE_Mac_API35` AVD 建立、啟動、安裝與停止腳本，所有 ADB 明確指定 `emulator-5580`。
- `MediaCodec.reset()` 後重新註冊 callback 的小型相容性修補；只改官方 APK 的 `classes4.dex`，使用每位使用者本機產生的測試簽章。
- 可從官方桌面發行包重建的 Mac 接收端、可選音訊統計與合成音／觸控測試 app 原始碼。
- 本機不透明 AAP relay，以及獨立的 Mac RFCOMM → WPP → CoreWLAN → TCP → 模擬器 AAP 橋接。
- Wi-Fi 變更前的還原紀錄、取消／逾時／斷線收尾、異常退出後的恢復入口與測試。
- 讓其他 Codex 或 agent 接手的 [AGENTS.md](AGENTS.md) 與 [操作手冊](docs/AGENT_RUNBOOK.md)。

不包含 SDK/JDK、AVD 磁碟映像、APK 發行檔、第三方 jar、私人 TLS／簽章金鑰、個人帳號、Wi-Fi 密碼、車輛識別或實驗原始錄音。這些產物會在明確的步驟下於使用者電腦取得或生成，並被 `.gitignore` 排除。

## 已知驗證範圍

| 項目 | 狀態 |
|---|---|
| 原測試環境的 Mac AARE 桌面畫面 | 已看到 1280×720 H.264，實際 fps 未量測 |
| 點選、手動拖曳捲動 | 原測試環境通過；自動化工具拖曳曾漏送 MOVE |
| 聲音 | 原環境收到 48 kHz 雙聲道 PCM，使用者確認合成雙音可聽見 |
| Phone screen、Google Maps 地圖載入 | 原環境通過；不是導航／定位驗證 |
| 舊映像內建 YouTube | 版本太舊、服務回應錯誤；未通過播放驗證 |
| 新 Mac 協調器、真 JVM WPP、原生 IPC、假無線電 | 本機整合測試通過 |
| 這份可攜專案的重新建置／測試 | 詳見 [驗證紀錄](docs/VALIDATION.md) |
| 實體 CoreWLAN 加入車機 AP、網路還原 | 尚未在真實車機上驗證 |
| EV6 憑證／AAP 接受、實車畫面／聲音／觸控 | **未完成驗證** |

參考平台：Apple Silicon Mac、macOS 26.7、16 GB RAM；Android API 35 `google_apis;arm64-v8a`，2 GB RAM／2 核。Intel Mac、其他 Android 映像、其他車機與長時間穩定性尚未驗證。原環境結果是人工／實機觀察，不是此 repo 在每台機器都會自動重現的保證。

## 從空白 checkout 開始

需要 Xcode Command Line Tools、完整 JDK 17（含 `javac`、`jpackage`）、Python 3.10+、Android 官方 SDK 命令列工具及 `ffmpeg`。詳見 [完整安裝步驟](docs/SETUP.md)，先自行處理 SDK 授權條款。

```sh
git clone https://github.com/joemaysong/aare-mac-emulator-bridge.git
cd aare-mac-emulator-bridge

# 依實際 JDK 安裝位置設定，不能只裝 JRE。
export JAVA_HOME="/path/to/jdk/Contents/Home"
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

python3 scripts/repro.py doctor
python3 scripts/repro.py fetch
python3 scripts/repro.py prepare-core
python3 scripts/repro.py build-core
python3 scripts/patch_apk.py
python3 scripts/repro.py build-desktop
python3 scripts/build_probe.py                    # 可選：合成音／觸控測試 APK
python3 scripts/repro.py create-avd               # 拒絕覆寫已存在的 AVD
python3 scripts/lab.py start --prepare-only       # 先啟動 Android 與 AARE，不開接收端
python3 scripts/lab.py install                    # 僅安裝到已核對名稱的 emulator-5580
python3 scripts/lab.py install --probe            # 可選
```

第一次 `prepare-only` 只會開好專用 AVD；若 AARE 尚未安裝，會提示先安裝而不開接收端。完成 `install` 後執行 `python3 scripts/lab.py prepare` 即可開啟 AARE。

在模擬器內按照 [設定與授權流程](docs/SETUP.md#aare-介面設定) 開啟 head-unit server、Phone screen、Accessibility 及需要時的 Entire screen 擷取。這些是使用者可見的權限，不會由腳本偷偷核准。

```sh
python3 scripts/lab.py start       # 開原始本機接收端，使用 adb forward 55277
python3 scripts/lab.py stop        # 只停止此 checkout 的接收端與專用 AVD
```

上游版本：[`v1.1.1`](https://github.com/prototux/AARE/releases/tag/v1.1.1)；原始碼 commit：[`e8da04dc422abd36be60a81bb9fc7f782e8d7e84`](https://github.com/prototux/AARE/tree/e8da04dc422abd36be60a81bb9fc7f782e8d7e84)。不要直接改成 `latest`。SDK 套件 ID 固定，但 Google 可能更新映像修訂版；建立時會記錄 `package.xml`，**不宣稱可以取得與原測試機位元完全相同的映像**。

## 不連車機的測試

```sh
zsh bridge/wireless-session/build.command
zsh bridge/wireless-session/test.command
python3 scripts/audit_public.py
```

這些步驟不使用車機 ADB、不啟動真實藍牙／Wi-Fi 連線。測試包含原生 Swift 還原政策、私有 IPC、真 JVM WPP 與二進位 relay；無線電由 fake 代替。

本機 Desktop 經 relay 的人工測試：先關閉已開啟的接收端，再執行 `python3 scripts/lab.py relay`；只能同時有一個接收端占用 AARE 的單一投影連線。Mac 假接收端的 `Parked` 是桌面模擬狀態，不能移植為實車限制繞過。

## 後續實車測試入口

先讀 [架構](docs/ARCHITECTURE.md) 與 [還原流程](docs/RECOVERY.md)。沒有當次實車測試授權時，只執行：

```sh
./bridge/wireless-session/start-wireless.command   # 預設只 --check
```

未來確認停妥、供電穩定且願意中斷現有投影後，才由使用者明確指定已配對車輛：

```sh
./bridge/wireless-session/start-wireless.command \
  --connect --device AA-BB-CC-DD-EE-FF --seconds 300
```

上例為占位位址。若新 SDP 查詢在特定裝置不回覆，可經核對後加 `--cached-service-diagnostic`；快取不等於新 SDP 驗證，仍必須通過真正 WPP。此工具不會啟動車機 AP 或修改車機。車機如果沒有送出 StartRequest／credentials，Mac 必須等待或收尾，不能偽造成功。

每輪報告的 `tcp_pair_connected` 只表示兩端 socket 已接上；`aap_tls_accepted` 與 `projection_verified` 仍需獨立證據。不要根據握手或傳輸 byte 數宣稱投影成功。

## 文件索引

- [SETUP：依賴、完整重建與 GUI 授權](docs/SETUP.md)
- [ARCHITECTURE：元件、資料流與責任界線](docs/ARCHITECTURE.md)
- [VALIDATION：已測／未測、測試指令與結果](docs/VALIDATION.md)
- [RECOVERY：取消、Wi-Fi 恢復、程式回退與移除](docs/RECOVERY.md)
- [AGENT_RUNBOOK：讓其他 agent 接手的逐階段工作單](docs/AGENT_RUNBOOK.md)
- [NOTICE：原作者、授權與修改範圍](NOTICE.md)
