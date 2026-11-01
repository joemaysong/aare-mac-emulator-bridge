# 停止、還原與移除

## 一般停止

Mac本機測試用 `python3 scripts/lab.py stop`；它只處理此 checkout 生成的桌面 app 與已核對名稱的 `emulator-5580`。不會 `killall java`、`adb kill-server`，也不處理其他裝置。

無線實驗用終端機 Ctrl-C。協調器停止自有 JVM／relay，關閉私有 IPC；原生程序看到 EOF／取消後執行 Wi-Fi 還原。看該輪 `runs/<run>/result.json`，**必須同時核對** `native_complete`、`wifi_restored`、`recovery_required`，不能只看程序 exit code 或無線圖示。

## Wi-Fi journal

檔案：`bridge/wireless-session/runtime/wifi-recovery.json`。

內容包括原 Wi-Fi 電源、SSID/BSSID、目標識別、介面和版本；不含密碼。加入前即寫入，0700目錄／0600檔案。journal代表「仍有義務核對／恢復」，不是刪掉便可略過的 cache。

原本Wi-Fi關閉：若目前仍是我們的目標或未連線，還原為關閉。原本已連網路：先核對仍是我們的目標，才斷開並等 macOS 重新加入原本已儲存網路。工具不猜密碼、不重寫全域網路服務順序，也不斷開使用者後來改選的其他網路。

如果結果是 `wifi_restored=false` 或 journal仍存在：

1. 保留 journal、原生回覆與當輪結果。不要直接刪檔、改狀態或把未核對的欄位改成true。
2. 確認原生背景工作是否仍在執行；若系統 Wi-Fi 呼叫卡住，它仍持有 radio.lock。不要同時開第二個調整工作。
3. 系統呼叫返回後，或原生程序已退出，再手動執行：

   ```sh
   ./bridge/wireless-session/recover-wifi.command
   ```

4. 恢復模式只處理既有紀錄，不開 Bluetooth、不啟動模擬器，也不連車機 TCP。
5. 若原網路需要輸密碼、沒有自動加入、BSSID已變、或使用者已切到另一網路，可能需使用者先在系統設定回到原狀，再重跑核對。沒有明確完成證據，就保留未完成狀態。

CoreWLAN被驅動／系統卡住時，無法保證固定時間內還原。協調器不會強殺仍可能負責還原的原生 worker後假裝成功；鎖可防止競爭修改，不能憑空完成系統呼叫。

## APK 還原

只針對專用模擬器。原始官方 APK 由 `dependencies.lock.json` 固定hash並保存於 `.cache/downloads/aare-1.1.1.apk`。本機修補版簽章不同，不能直接以 `adb install -r` 跨簽章切換。

如確定要回原版，先保存必要設定並確認可接受 AARE app資料重置，再明確指定：

```sh
adb -s emulator-5580 emu avd name
# 輸出必須是 AARE_Mac_API35，否則停止。
adb -s emulator-5580 uninstall net.prototux.aare
adb -s emulator-5580 install .cache/downloads/aare-1.1.1.apk
```

原版可能在相同 emulator encoder上再次黑畫面；還原簽章不等於解決相容性問題。不要將這些步驟套到車機或其他手機。

## 程式碼回退

本 repo 是獨立整合工程，不覆寫上游原始 checkout或車機候選版。需要回退時，先完成活動 session／journal的網路還原，再切回已知正常的Git commit重建；generated classpath與app-image必須針對當前路徑重新產生。

不要刪除原生app或runtime後才處理未完成journal；那會讓還原工具與證據一起消失。

## 移除

先停止自己的本機與無線工作、核對無未完成journal。AVD若確定不再需要，使用者可在 Android Device Manager刪除專用 `AARE_Mac_API35`；它包含模擬器內資料，不能把刪除當成無損清 cache。

之後可移除此 checkout 的 `.cache`、`build`、`bridge/core`、各個generated `build/apps/runtime/evidence/runs`。Android SDK、JDK、ffmpeg與Gradle cache可能被其他專案共用，**不列入自動移除範圍**。所有歷次run檔案若含網路識別或媒體資料，保留／清理請依使用者需求處理。
