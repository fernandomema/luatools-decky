import React, { FC, useState, useCallback, useEffect } from "react";
import { callable } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem, showContextMenu, Menu, MenuItem, DialogButton } from "@decky/ui";
import type { ApiResponse, InstalledScript } from "../types/api";

const getScripts = callable<[], ApiResponse & { scripts: InstalledScript[] }>("get_installed_lua_scripts");
const deleteApp = callable<[number], ApiResponse>("delete_luatools_for_app");
const refreshGames = callable<[], ApiResponse & { apps: { appid: number; name: string }[] }>("read_loaded_apps");
const dismiss = callable<[], ApiResponse>("dismiss_loaded_apps");

const InstalledGamesPanel: FC = () => {
  const [scripts, setScripts] = useState<InstalledScript[]>([]);
  const [loadedApps, setLoadedApps] = useState<{ appid: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await getScripts();
    if (res.success && res.scripts) setScripts(res.scripts);
    const apps = await refreshGames();
    if (apps.success && apps.apps) setLoadedApps(apps.apps);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (appid: number) => {
    await deleteApp(appid);
    load();
  }, [load]);

  const handleDismiss = useCallback(async () => {
    await dismiss();
    load();
  }, [load]);

  if (loading) return <PanelSection><PanelSectionRow>Loading installed games...</PanelSectionRow></PanelSection>;

  return (
    <PanelSection>
      <PanelSectionRow>
        <div style={{ fontWeight: 700 }}>Installed Games ({scripts.length})</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={handleDismiss}>Clear List</ButtonItem>
      </PanelSectionRow>

      {scripts.length === 0 && loadedApps.length === 0 && (
        <PanelSectionRow>
          <div style={{ color: "#888", textAlign: "center", padding: "20px", width: "100%" }}>
            No games installed yet.
          </div>
        </PanelSectionRow>
      )}

      {scripts.map((script) => (
        <PanelSectionRow key={script.appid}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", opacity: script.isDisabled ? 0.6 : 1 }}>
            <div style={{ cursor: "pointer", flex: 1 }} onClick={() => window.open(`https://steamcommunity.com/app/${script.appid}`, '_blank')}>
              <div style={{ fontWeight: "bold", fontSize: "14px" }}>
                {script.gameName}
                {script.isDisabled && <span style={{ color: "#ff9800", marginLeft: "6px", fontSize: "11px" }}>[Disabled]</span>}
              </div>
              <div style={{ fontSize: "11px", color: "#888" }}>
                AppID: {script.appid} | {script.modifiedDate} | {(script.fileSize / 1024).toFixed(1)} KB
              </div>
            </div>
            <DialogButton
              style={{ minWidth: 0, width: 36, padding: "4px 0", flexShrink: 0 }}
              onClick={() => showContextMenu(
                <Menu label="Actions">
                  <MenuItem onClick={() => window.open(`https://steamcommunity.com/app/${script.appid}`, '_blank')}>Open Store</MenuItem>
                  <MenuItem onClick={() => handleDelete(script.appid)}>Delete</MenuItem>
                </Menu>
              )}
            >⋯</DialogButton>
          </div>
        </PanelSectionRow>
      ))}

      {loadedApps
        .filter((a) => !scripts.find((s) => s.appid === a.appid))
        .map((app) => (
          <PanelSectionRow key={app.appid}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
              <div style={{ cursor: "pointer", flex: 1 }} onClick={() => window.open(`https://steamcommunity.com/app/${app.appid}`, '_blank')}>
                <div style={{ fontSize: "14px" }}>{app.name}</div>
                <div style={{ fontSize: "11px", color: "#888" }}>AppID: {app.appid}</div>
              </div>
              <ButtonItem layout="below" onClick={() => handleDelete(app.appid)}>Remove</ButtonItem>
            </div>
          </PanelSectionRow>
        ))}
    </PanelSection>
  );
};

export default InstalledGamesPanel;
