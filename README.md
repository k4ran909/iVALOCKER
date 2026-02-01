<div align="center">

  <img src="web/assets/logo.png" alt="iVALOCKER Logo" width="200" height="200" />

  # iVALOCKER
  ### by [k4ran909](https://github.com/k4ran909)

  **The Fastest VALORANT Agent Instalocker**
  
  [![Downloads](https://img.shields.io/github/downloads/k4ran909/iVALOCKER/total?style=for-the-badge&logo=github&color=ff4655)](https://github.com/k4ran909/iVALOCKER/releases)
  [![Latest Release](https://img.shields.io/github/v/release/k4ran909/iVALOCKER?style=for-the-badge&logo=rocket&color=ff4655)](https://github.com/k4ran909/iVALOCKER/releases/latest)
  [![License](https://img.shields.io/github/license/k4ran909/iVALOCKER?style=for-the-badge&color=blue)](LICENSE)

  <br>
  
  <a href="https://github.com/k4ran909/iVALOCKER/releases/latest">
    <img src="https://img.shields.io/badge/DOWNLOAD_NOW-FF4655?style=for-the-badge&logo=windows&logoColor=white" height="50">
  </a>

</div>

<br>

## ⚡ Features

- **🚀 Zero Delay Locking**  
  Optimized with a **10ms polling rate** for the fastest possible lock speed. No human can beat this.

- **🎯 Instant Selection**  
  Bypasses the selection animation and goes straight for the lock.

- **🎨 Beautiful UI**  
  A sleek, modern interface with smooth animations, agent banners, and search functionality.

- **🛡️ Safe & Secure**  
  Interacts only with the local Riot Client API (like a wrapper). Does not read memory or inject code.

<br>

## 🎮 How to Use

1. **Download** the latest `iVALOCKER_k4ran909.exe` from [Releases](https://github.com/k4ran909/iVALOCKER/releases).
2. **Open VALORANT** and log in to the main menu.
3. **Run iVALOCKER** (Run as Administrator if needed).
4. **Select your Agent** from the list. The status will change to `WAITING FOR PRE-GAME`.
5. **Queue for a Match**. As soon as agent select appears, your agent will be locked instantly!

> **Note:** Windows SmartScreen might warn you because the app is not signed. Click `More Info` > `Run Anyway`. This is normal for open-source tools.

<br>

## 🛠️ Building from Source

If you prefer to build it yourself:

1. **Clone the repo**
   ```bash
   git clone https://github.com/k4ran909/iVALOCKER.git
   cd iVALOCKER
   ```

2. **Install Dependencies** (Python < 3.12 recommended)
   ```bash
   pip install -r requirements.txt
   ```

3. **Build EXE**
   ```bash
   python -m eel main.py web --onefile --noconsole --icon=./web/favicon.ico --name="iVALOCKER_k4ran909" --add-data="web;web"
   ```

<br>

## ⚠️ Disclaimer

This software is for **educational purposes only**.
- I (k4ran909) am not responsible for any bans or suspensions. 
- While API abuse bans are extremely rare (and usually only 7 days if they happen), use this tool at your own risk.
- This tool is not affiliated with Riot Games or VALORANT.

<br>

## ❤️ Credits

- Built with [Eel](https://github.com/python-eel/Eel) and [valclient](https://github.com/colinhartigan/valclient.py)
- Inspired by various open-source instalockers
- Agent art and assets belong to Riot Games

<div align="center">
  <br>
  Designed & Maintained by <a href="https://github.com/k4ran909"><b>k4ran909</b></a>
</div>