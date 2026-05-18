# LuaTools Decky

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for Steam Deck that lets you download and manage games through **ACCELA** + **SLSsteam** integration — with full controller support.

> Ported to Decky by **fernandomema**, based on the original [LuaToolsLinux](https://github.com/Star123451/LuaToolsLinux) by **StarWarsK**.

---

## Features

### 🎮 Add Game
Download games directly to any Steam library (internal or SD card) using manifest sources (Morrenus/Hubcap). Tracks real-time download progress in MB.

### 📦 Installed
Browse all installed lua scripts. Open game folders, remove scripts, and manage entries from a controller-friendly list.

### 🔧 Fixes
Search and apply community game fixes by AppID. View and remove applied fixes.

### 🛠️ Workshop
Download Steam Workshop items by AppID + PublishedFileID with real-time progress bar.

### ⚙️ SLSsteam
Manage SLSsteam engine settings:
- Toggle **PlayNotOwnedGames**
- Add / remove **FakeAppIds**, **App Tokens**, and **DLCs** per game

### ⚙️ Settings
- Morrenus API key
- Ryuu cookie
- Launcher path (ACCELA / Bifrost)
- Workshop tool path (DepotDownloaderMod)
- Check for updates
- Restart Steam

---

## Requirements

| Dependency | Notes |
|---|---|
| [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) | Plugin loader for Steam Deck |
| [ACCELA](https://github.com/Star123451/LuaToolsLinux) | Backend launcher (set path in Settings) |
| [SLSsteam](https://github.com/nicholasgasior/SLSsteam) | Required for PlayNotOwnedGames support |
| [DepotDownloaderMod](https://github.com/SteamRE/DepotDownloader) | Used for downloading game depots |

---

## Installation

### Via Decky (recommended)
1. Open Decky Loader → Store
2. Search for **LuaTools**
3. Install

### Manual
```bash
# Clone into your Decky plugins folder
git clone https://github.com/fernandomema/luatools-decky \
  ~/homebrew/plugins/LuaTools-Decky
```
Then restart Decky: `sudo systemctl restart plugin_loader.service`

---

## Building from source

```bash
# Install dependencies
pnpm install

# Build frontend
pnpm build

# The dist/ folder is the built plugin — symlink or copy to plugins folder
```

---

## How it works

1. Fetches game manifests from configured API sources (Morrenus, Hubcap, Ryuu, Sushi, Spinoza)
2. Runs **DepotDownloaderMod** to download depot files into the chosen Steam library
3. Generates a proper `appmanifest_XXXXX.acf` and registers the game in `libraryfolders.vdf`
4. Installs the lua script to `~/.steam/steam/config/stplug-in/`
5. SLSsteam picks up the new AppID and makes Steam show and launch the game

---

## License

MIT
