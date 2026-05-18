import React, { FC, useState, useCallback, useEffect } from "react";
import { callable } from "@decky/api";
import { ButtonItem, PanelSection, TextField } from "@decky/ui";
import type { ApiResponse } from "../types/api";

const getMorrenusKey = callable<[], ApiResponse>("get_settings_config");
const updateKey = callable<[string], ApiResponse>("update_morrenus_key");
const saveCookie = callable<[string], ApiResponse>("save_ryu_cookie");
const getLauncherPath = callable<[], ApiResponse & { path: string }>("get_launcher_path");
const saveLauncherPath = callable<[string], ApiResponse>("save_launcher_path");
const browseLauncher = callable<[], ApiResponse & { path: string }>("browse_for_launcher");
const getWorkshopPath = callable<[], ApiResponse & { path: string }>("get_workshop_tool_path");
const saveWorkshopPath = callable<[string], ApiResponse>("save_workshop_tool_path");
const restartSteam = callable<[], ApiResponse>("restart_steam");
const checkUpdates = callable<[], ApiResponse & { update_available: boolean; version?: string }>("check_for_updates_now");

const SettingsPanel: FC = () => {
  const [morrenusKey, setMorrenusKey] = useState("");
  const [ryuuCookie, setRyuuCookie] = useState("");
  const [launcherPath, setLauncherPath] = useState("");
  const [workshopPath, setWorkshopPath] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const cfg = await getMorrenusKey();
    if (cfg.success && cfg.values && cfg.values.morrenusKey) {
      setMorrenusKey(cfg.values.morrenusKey);
    }
    const lp = await getLauncherPath();
    if (lp.success && lp.path) setLauncherPath(lp.path);
    const wp = await getWorkshopPath();
    if (wp.success && wp.path) setWorkshopPath(wp.path);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSaveKey = useCallback(async () => {
    const res = await updateKey(morrenusKey);
    setMsg(res.message || res.error || "");
  }, [morrenusKey]);

  const handleSaveCookie = useCallback(async () => {
    const res = await saveCookie(ryuuCookie);
    setMsg(res.message || res.error || "");
  }, [ryuuCookie]);

  const handleSaveLauncher = useCallback(async () => {
    const res = await saveLauncherPath(launcherPath);
    setMsg(res.message || res.error || "");
  }, [launcherPath]);

  const handleBrowseLauncher = useCallback(async () => {
    const res = await browseLauncher();
    if (res.success && res.path) setLauncherPath(res.path);
  }, []);

  const handleSaveWorkshop = useCallback(async () => {
    const res = await saveWorkshopPath(workshopPath);
    setMsg(res.message || res.error || "");
  }, [workshopPath]);

  const handleCheckUpdates = useCallback(async () => {
    const res = await checkUpdates();
    if (res.update_available) setMsg(`Update available: ${res.version}`);
    else setMsg("Already up to date");
  }, []);

  return (
    <>
      <PanelSection title="Morrenus API Key">
        <TextField
          value={morrenusKey}
          onChange={(e) => setMorrenusKey(e.target.value)}
        />
        <ButtonItem layout="below" onClick={handleSaveKey}>
          Save Key
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Ryuu Cookie">
        <TextField
          value={ryuuCookie}
          onChange={(e) => setRyuuCookie(e.target.value)}
        />
        <ButtonItem layout="below" onClick={handleSaveCookie}>
          Save Cookie
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Launcher Path (ACCELA/Bifrost)">
        <TextField
          value={launcherPath}
          onChange={(e) => setLauncherPath(e.target.value)}
        />
        <ButtonItem layout="below" onClick={handleSaveLauncher}>
          Save Path
        </ButtonItem>
        <ButtonItem layout="below" onClick={handleBrowseLauncher}>
          Browse
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Workshop Tool Path">
        <TextField
          value={workshopPath}
          onChange={(e) => setWorkshopPath(e.target.value)}
        />
        <ButtonItem layout="below" onClick={handleSaveWorkshop}>
          Save Path
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Updates">
        <ButtonItem layout="below" onClick={handleCheckUpdates}>
          Check for Updates
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Steam">
        <ButtonItem layout="below" onClick={async () => {
          const r = await restartSteam();
          setMsg(r.message || (r.success ? "Restarting..." : "Failed"));
        }}>
          Restart Steam
        </ButtonItem>
      </PanelSection>

      {msg && (
        <PanelSection title="Status">
          <div style={{ padding: "6px", fontSize: "13px" }}>{msg}</div>
        </PanelSection>
      )}
    </>
  );
};

export default SettingsPanel;
