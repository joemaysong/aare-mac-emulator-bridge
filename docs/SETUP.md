# 完整安裝與重建

本流程的預設終點是 **Mac 本機 Android + AARE 桌面投影**，不需要車機。命令從 repository 根目錄執行；路徑可含空白，請保留引號。

## 1. 主機需求

- Apple Silicon Mac；原觀察平台 macOS 26.7、16 GB RAM。其他 macOS 版本與 Intel 未驗證。
- 預留約20 GB可用空間供 SDK、Android 映像、AVD、JDK、Gradle cache 與 app-image。這不是 source repo 的大小。
- Python 3.10+、Git、Xcode Command Line Tools／Xcode（`xcrun swiftc`、`codesign`）。
- 完整 JDK 17，須包含 `java`、`javac`、`jar`、`keytool`、`jpackage`。原環境使用 Eclipse Temurin 17.0.21+9；JRE 不足以重建。JDK21尚未作為本包實際測試基準。
- [Android 官方 SDK 命令列工具](https://developer.android.com/tools)；安裝與授權由使用者完成。
- `ffmpeg`，提供桌面接收端 H.264 解碼。可以使用官方列出的 macOS 套件或 Homebrew 的 `ffmpeg`，不要把來路不明的可執行檔放入 PATH。

常用前置命令（安裝軟體、條款與作業系統對話框由使用者處理）：

```sh
xcode-select --install
# 安裝官方 Eclipse Temurin/OpenJDK 17 後：
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
java -version
javac -version
jpackage --version
ffmpeg -version
```

若 JDK 是解壓到自選目錄而未註冊系統，請直接設定其 `Contents/Home`，不要照抄原作者工作站路徑。若沒有 Homebrew，不必為此 repository 自動安裝它；可選擇已有的官方工具安裝方式。

## 2. Android SDK 套件

先把 Android 官方命令列工具安裝到 SDK 的 `cmdline-tools/latest/`，自行閱讀並處理 SDK 授權：

```sh
sdkmanager --sdk_root="$ANDROID_SDK_ROOT" --licenses
sdkmanager --sdk_root="$ANDROID_SDK_ROOT" \
  'platform-tools' 'emulator' 'platforms;android-35' 'build-tools;35.0.0' \
  'system-images;android-35;google_apis;arm64-v8a'
```

不要用 `yes | sdkmanager --licenses` 把法律條款當成一般確認。新版本 SDK 可能提示改用 Android CLI；此處列出的 sdkmanager 相容入口在重建時仍可用，若未來移除，應另行更新文件並驗證。

這裡是 **Google APIs** 映像，不是 **Google Play** 映像。不要額外下載 API36／Play 映像。包名固定不代表檔案 revision 永遠相同：`create-avd` 會保存當次映像 `package.xml` 到 `build/installed-system-image-package.xml`。原機 emulator37.2.13、platform-tools37.0.1；官方 repository 後續更新未逐版驗證。

```sh
python3 scripts/repro.py doctor
```

預期：Apple Silicon、完整 JAVA_HOME、所有 SDK 檔案與 ffmpeg 存在。doctor 不下載、不執行 ADB、不操作無線電。

## 3. 取得鎖定的上游依賴

```sh
python3 scripts/repro.py fetch
```

只下載 `dependencies.lock.json` 指定的官方 AARE APK／桌面發行包／原始碼壓縮檔，以及 Maven Central 的 smali 工具依賴。每個檔案都驗證 SHA-256；不允許 digest 不符時繼續。沒有下載 Android 映像、Google Maps、YouTube、其他 APK 或 JDK。

若有既有 cache，可用 `fetch --from-cache /path/to/cache`；只有鎖定清單內且 hash 正確的檔案會被複製，不會掃描或帶走整個目錄。下載 cache 位於 `.cache/downloads`，不提交 Git。

## 4. 重建 JVM 協定核心

```sh
python3 scripts/repro.py prepare-core
python3 scripts/repro.py build-core
```

來源固定到 AARE commit `e8da04dc422abd36be60a81bb9fc7f782e8d7e84`。`prepare-core` 在 `bridge/core` 生成只含 `aap` 的 Gradle 工程，停用 Android／headunit 模組與 Google Gradle repository，使用 Maven Central 與 plugin portal；不改 `.cache/upstream`。

額外 task `:aap:writeMacClasspath` 產生當前 checkout 的 JVM classpath；它包含絕對路徑，因此換目錄／換機器後必須重跑，不可把舊檔當成可攜產物。建置使用 `--no-configuration-cache`，避免該 task 擷取 Gradle 物件造成序列化錯誤。

初次 Gradle 建置會下載 pinned Gradle/Maven 依賴。已有正確 cache 時可用 `build-core --offline`；不要把第一次離線缺依賴誤判成原始碼失敗。上游 `aap` 測試也會在這一步執行。

## 5. 產生模擬器相容 APK

```sh
python3 scripts/patch_apk.py
```

官方1.1.1在原測試 AVD 上因 `c2.android.avc.encoder` 不接受某個 format 選項而走 fallback；`MediaCodec.reset()` 清掉非同步 callback，導致沒有畫面。修補只在 reset 後重註冊 `Callback` 與 encoder handler，見 [來源等價 patch](../patches/VideoEncoder.compat.patch)。

可執行配方會：

1. 驗證官方 APK SHA-256。
2. 解出 `classes4.dex`，使用固定 smali2.5.2 反組譯。
3. 確認唯一 reset 呼叫與 register 形狀符合指定版本；不符合就停止。
4. 只在 `VideoEncoder.smali` 插入重新註冊，重組 dex。
5. 核對所有其他 ZIP 內容完全未變（舊簽章 metadata 除外）。
6. zipalign，使用 `.cache/signing/emulator-debug.jks` 的新本機測試 key 簽署並驗證。

產物：`build/apk-patch/aare-emulator.apk` 與 `verification.json`。**不同機器會產生不同簽章／APK hash，不能拿一個全域 patched APK hash 判斷失敗**；原版 APK、patch 形狀和未改內容才是固定驗證點。這不是原作者官方簽章，也不是車機 firmware。

腳本拒絕覆寫已有工作目錄；重跑前可先將自己產生的 `build/apk-patch` 移到另一個名稱保存。不要改成清除整個 repository。

## 6. 建立桌面接收端與可選測試 app

```sh
python3 scripts/repro.py build-desktop
python3 scripts/build_probe.py
```

桌面使用官方 AARE headunit 發行包的 jar，加入相同播放介面的音訊統計 overlay，再由 `jpackage` 在當前機器產生兩個 app-image：

- `bridge/emulator-lab/apps/AARE Desktop.app`：直連127.0.0.1:55277。
- `bridge/emulator-lab/apps/AARE Bridge Desktop.app`：連本機relay的55278。

每個 app 包含自己的 Java runtime，不應把原測試機帶有外部 SDK symlink 的 app 直接複製給別人。兩個 app 都由本機 ad-hoc codesign。

可選測試 APK `build/probe/AARE-Lab.apk` 只包含觸控計數與3秒合成音：48 kHz PCM16、先440 Hz後660 Hz、低振幅。沒有錄音或網路權限；不會自動播放。其 Android manifest／原始碼與 D8/aapt2/apksigner 配方都在此 repo。

## 7. 建立與安裝專用 AVD

```sh
python3 scripts/repro.py create-avd
python3 scripts/lab.py start --prepare-only
python3 scripts/lab.py install
python3 scripts/lab.py install --probe
python3 scripts/lab.py prepare
```

AVD名稱 `AARE_Mac_API35`、API35 ARM64、2048 MB、2 cores、720×1280／240dpi、host GPU；啟動用 port5580，即 `emulator-5580`。若同名 AVD 已存在，建立腳本會拒絕覆寫。不要用 `--force` 擦掉使用者現有 AVD。

如果 `adb install -r` 因官方／本機簽章不同失敗，先保存必要資料，經使用者同意後只卸載**專用模擬器內**的 `net.prototux.aare` 再安裝。不要到其他 ADB 裝置重試，也不要把金鑰複製到公開 repo。

## AARE 介面設定

在專用模擬器的 AARE1.1.1 裡依序核對：

1. Advanced：開啟 head-unit server，端點 `localabstract:aare_hu`；不必開 LAN accept。
2. Advanced：開啟 Phone screen on server。
3. Car screen：開啟 Phone screen。
4. Android Accessibility：由使用者啟用 AARE 的 MirrorTouchService，讓鏡像觸控能回送。
5. Car audio：若要投影模擬器的音訊，進 Screen-capture permission，同意必要的模擬器錄音／媒體擷取權限，選 **Entire screen**，不是單一 app。
6. 擷取授權後開接收端，離開再進入 Phone screen 以使用新 token。開機前的 token、等太久的 token 或已失效 token 不能當成仍有擷取權限。

```sh
python3 scripts/lab.py start
```

桌面接收端是假的 head unit；在停車的本機測試中勾選 `Parked`，才可顯示受限制的 Phone screen。這個選項只用於 Mac 模擬測試，不能套用到真車。

若第一次看到憑證確認，先確認是在自己建立的模擬器與本機 headunit之間，再依正常 AARE 流程信任；不要略過 TLS 檢查或匯入來路不明的生產金鑰。本專案不提供官方 Google AA 私鑰。

## 8. 畫面、聲音與觸控驗收

先閱讀 [VALIDATION.md](VALIDATION.md)。手動確認看得到畫面；在投影內操作設定並確認模擬器真的變動；用手動拖曳核對捲動；進 AARE Lab 播放合成音，確認 Mac 有聲音且 audio-stats 的收到／播放 byte 增加。

不要只根據「點擊工具回傳成功」就記 PASS。原實驗中自動工具曾只送 DOWN/UP 沒有 MOVE，必須人工驗證拖曳。

Mac本機relay：關閉直連接收端後執行 `python3 scripts/lab.py relay`，重做上述檢查。`lab.py stop` 只停此 checkout 的接收端與已核對名稱的專用 AVD，不會停止其他 Java、ADB server或車機。

## 9. Maps 與 YouTube 的界線

原 Google APIs 映像內建的是完整 Maps／YouTube APK，但官方 Google AA 發送端只有stub。AARE 是另外的發送端，Mac Desktop 是接收端；兩者不是Android emulator裡的同一個 app。

原實驗 Maps11.129.0103載入地圖且能鏡像，沒有驗證路線、GPS或導航語音。YouTube19.17.42太舊，要求更新／搜尋400，不能宣稱影片播放成功。映像的測試簽章也可能使 Google 正式版不能直接覆蓋。

此 repo 不下載地圖／影片 app、不提供APK來源，也不建立第二台Google Play AVD。新映像若內建版本不同，應記錄實際版本，重新驗證，不沿用舊結果。
