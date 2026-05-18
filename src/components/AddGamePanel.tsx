import React, { FC, useState, useCallback, useEffect, useRef } from "react";
import { callable, fetchNoCors } from "@decky/api";
import {
  PanelSection,
  PanelSectionRow,
  TextField,
  ButtonItem,
  DropdownItem,
  ProgressBarWithInfo,
  Field,
  DialogButton,
} from "@decky/ui";
import type { ApiResponse, DownloadState, SteamLibrary } from "../types/api";

const startAdd = callable<[number, string], ApiResponse>("start_add_via_luatools");
const getStatus = callable<[number], ApiResponse & { state: DownloadState }>("get_add_status");
const cancelAdd = callable<[number], ApiResponse>("cancel_add_via_luatools");
const getLibraries = callable<[], ApiResponse & { libraries: SteamLibrary[] }>("get_steam_libraries");
const hasLua = callable<[number], ApiResponse & { exists: boolean }>("has_luatools_for_app");
const addToken = callable<[number], ApiResponse>("add_game_token");
const addFakeId = callable<[number], ApiResponse>("add_fake_app_id");
const removeFakeId = callable<[number], ApiResponse>("remove_fake_app_id");
const checkFakeId = callable<[number], ApiResponse & { exists: boolean }>("check_fake_app_id_status");
const addDlcs = callable<[number], ApiResponse>("add_game_dlcs");
const checkUpdate = callable<[number], ApiResponse>("check_game_update");

const SELECTED_LIB_KEY = "luatools_selectedLib";
const ACTIVE_APPID_KEY = "luatools_activeAppid";

const AddGamePanel: FC = () => {
  const [appid, setAppidState] = useState<string>(() => {
    try { return sessionStorage.getItem(ACTIVE_APPID_KEY) || ""; } catch { return ""; }
  });
  const setAppid = useCallback((v: string) => {
    setAppidState(v);
    try { sessionStorage.setItem(ACTIVE_APPID_KEY, v); } catch {}
  }, []);
  const [lastVisitedAppid, setLastVisitedAppid] = useState<string | null>(null);
  const [savedGameName, setSavedGameName] = useState<string | null>(null);
  const [savedGameImage, setSavedGameImage] = useState<string | null>(null);
  const [status, setStatus] = useState<DownloadState | null>(null);
  const [exists, setExists] = useState(false);
  const [updateStatus, setUpdateStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [libraries, setLibraries] = useState<SteamLibrary[]>([]);
  const [selectedLib, setSelectedLib] = useState<string>(() => {
    try { return sessionStorage.getItem(SELECTED_LIB_KEY) || ""; } catch { return ""; }
  });
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const handleLibChange = useCallback((path: string) => {
    setSelectedLib(path);
    try { sessionStorage.setItem(SELECTED_LIB_KEY, path); } catch {}
  }, []);

  useEffect(() => {
    getLibraries().then(r => {
      if (r.success && r.libraries?.length) {
        setLibraries(r.libraries);
        // Only set default if nothing persisted yet
        setSelectedLib(prev => {
          if (prev && r.libraries.find((l: any) => l.path === prev)) return prev;
          try { sessionStorage.setItem(SELECTED_LIB_KEY, r.libraries[0].path); } catch {}
          return r.libraries[0].path;
        });
      }
    }).catch(() => {});

    try {
      const saved = window.localStorage.getItem('luatools_lastVisitedAppid');
      if (saved) setLastVisitedAppid(saved);
    } catch (e) {}
  }, []);

  useEffect(() => {
    // Fetch Steam store metadata for the saved appid to show name and image
    const id = lastVisitedAppid;
    if (!id) return;
    (async () => {
      try {
        const resp: any = await fetchNoCors(`https://store.steampowered.com/api/appdetails?appids=${id}&l=english`);
        let data: any = null;
        if (typeof resp?.json === 'function') {
          data = await resp.json();
        } else if (typeof resp?.text === 'function') {
          data = JSON.parse(await resp.text());
        }
        if (data && data[id] && data[id].success && data[id].data) {
          setSavedGameName(data[id].data.name || null);
          // header_image is usually available
          setSavedGameImage(data[id].data.header_image || data[id].data.img_logo_url || null);
        }
      } catch (e) {
        // ignore
      }
    })();
  }, [lastVisitedAppid]);

  const handleAdd = useCallback(async () => {
    const id = parseInt(appid);
    if (!id || id <= 0) return;
    setLoading(true);
    setUpdateStatus("");

    const check = await hasLua(id);
    setExists(check.exists ?? false);

    const res = await startAdd(id, selectedLib);
    if (res.success) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(async () => {
        const s = await getStatus(id);
        setStatus(s.state ?? null);
        if (s.state?.status === "done" || s.state?.status === "failed" || s.state?.status === "cancelled") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          setLoading(false);
        }
      }, 1000);
    } else {
      setLoading(false);
    }
  }, [appid, selectedLib]);

  const handleCancel = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    await cancelAdd(id);
    if (intervalRef.current) clearInterval(intervalRef.current);
    setLoading(false);
  }, [appid]);

  const handleAddToken = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    const res = await addToken(id);
    setUpdateStatus(res.message || res.error || "");
  }, [appid]);

  const handleAddFakeId = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    const check = await checkFakeId(id);
    if (check.exists) {
      const res = await removeFakeId(id);
      setUpdateStatus(res.message || res.error || "FakeAppId removed");
    } else {
      const res = await addFakeId(id);
      setUpdateStatus(res.message || res.error || "");
    }
  }, [appid]);

  const handleAddDlcs = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    const res = await addDlcs(id);
    setUpdateStatus(res.message || res.error || "");
  }, [appid]);

  const handleCheckUpdate = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    const res = await checkUpdate(id);
    setUpdateStatus(res.status || res.error || "");
  }, [appid]);

  const handleDetect = useCallback(async () => {
    setUpdateStatus("Detectando...");
    try {
      const res = await fetchNoCors("http://localhost:8080/json");
      let tabs: any[];
      if (typeof res === "object" && res !== null && "result" in res) {
        tabs = JSON.parse((res as any).result.body);
      } else {
        tabs = await (res as any).json();
      }
      const storeTab = tabs.find((t: any) => t.url?.includes("store.steampowered.com/app/"));
      if (storeTab) {
        const match = storeTab.url.match(/\/app\/(\d+)/);
        if (match) {
          setAppid(match[1]);
          setUpdateStatus(`Detectado: ${match[1]}`);
          return;
        }
      }
      setUpdateStatus("No se encontró tienda abierta");
    } catch (e) {
      setUpdateStatus(`Error: ${e}`);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const progress = status?.totalBytes && status?.bytesRead
    ? Math.round((status.bytesRead / status.totalBytes) * 100)
    : 0;

  const libOptions = libraries.map(lib => ({
    label: `${lib.label} (${lib.free} GB free)`,
    data: lib.path,
  }));

  const formatBytes = (b: number) => {
    if (b <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let u = 0;
    let n = b;
    while (n >= 1024 && u < units.length - 1) {
      n = n / 1024;
      u++;
    }
    return `${n.toFixed(n < 10 && u > 0 ? 1 : 0)} ${units[u]}`;
  };

  // If we have a saved last visited appid and the user hasn't typed anything, show it
  if (!appid && lastVisitedAppid) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            {savedGameImage && (
              // eslint-disable-next-line jsx-a11y/img-redundant-alt
              <img src={savedGameImage} alt="game image" style={{ width: 80, height: 45, objectFit: "cover", borderRadius: 6 }} />
            )}
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{savedGameName ?? `AppID: ${lastVisitedAppid}`}</div>
              <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{`AppID: ${lastVisitedAppid}`}</div>
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" bottomSeparator="none" onClick={() => { setAppid(lastVisitedAppid); }} disabled={loading}>{loading ? "Downloading..." : "Download"}</ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" bottomSeparator="none" onClick={() => { try { window.localStorage.removeItem('luatools_lastVisitedAppid'); } catch (e) {}; setLastVisitedAppid(null); setSavedGameName(null); setSavedGameImage(null); }}>Clear</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  // If there's no appid typed and no saved last visited, show the empty state
  if (!appid) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label="Open a game in the store" childrenLayout="below">
            <div style={{ display: "flex", gap: "8px", marginTop: "6px" }}>
              <DialogButton onClick={handleDetect} disabled={loading} style={{ minWidth: "40px", padding: "4px 8px" }}>🔍</DialogButton>
              <div style={{ color: "#888", fontSize: "13px", alignSelf: "center" }}>Open a game's store page in the browser to detect it.</div>
            </div>
          </Field>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  // Otherwise render the normal options UI for the provided appid but hide the AppID input
  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            {savedGameImage && (
              // eslint-disable-next-line jsx-a11y/img-redundant-alt
              <img src={savedGameImage} alt="game image" style={{ width: 80, height: 45, objectFit: "cover", borderRadius: 6 }} />
            )}
            <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{savedGameName ?? `AppID: ${appid}`}</div>
              <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{`AppID: ${appid}`}</div>
            </div>
          </div>
        </PanelSectionRow>
      </PanelSection>

      {libraries.length > 0 && (
        <PanelSection title="Destination">
          <PanelSectionRow>
            <DropdownItem
              rgOptions={libOptions}
              selectedOption={selectedLib}
              onChange={(opt) => handleLibChange(opt.data)}
            />
          </PanelSectionRow>
        </PanelSection>
      )}

      <PanelSection title="Download">
        <PanelSectionRow>
          <ButtonItem layout="below" bottomSeparator="none" onClick={handleAdd} disabled={loading || !appid}>
            {loading
              ? (status?.status === "downloading" && status?.totalBytes && status.totalBytes > 0
                  ? `Descargando... ${formatBytes(status.bytesRead ?? 0)} / ${formatBytes(status.totalBytes)}`
                  : status?.message ?? "Downloading...")
              : "Download"}
          </ButtonItem>
        </PanelSectionRow>
        {loading && (
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={handleCancel}>Cancel</ButtonItem>
          </PanelSectionRow>
        )}
        {status && (
          <>
            <PanelSectionRow>
              <Field label={`Estado: ${status.status}`} childrenLayout="below">
                {status.currentApi && <div style={{ fontSize: "12px" }}>API: {status.currentApi}</div>}
                {status.message && <div style={{ fontSize: "12px", marginTop: "4px" }}>{status.message}</div>}
                {status.error && <div style={{ fontSize: "12px", marginTop: "4px", color: "red" }}>Error: {status.error}</div>}
              </Field>
            </PanelSectionRow>
            {status.status === "downloading" && status.totalBytes && status.totalBytes > 0 && (
              <PanelSectionRow>
                <ProgressBarWithInfo
                  nProgress={progress}
                  sOperationText={`${formatBytes(status.bytesRead ?? 0)} / ${formatBytes(status.totalBytes)}`}
                />
              </PanelSectionRow>
            )}
            {status.status === "downloading_game" && (
              <PanelSectionRow>
                <ProgressBarWithInfo
                  nProgress={status.percent != null ? Math.min(status.percent, 100) : 0}
                  sOperationText="Descargando archivos del juego..."
                  sTimeRemaining={status.percent != null ? `${status.percent.toFixed(1)}%` : undefined}
                />
              </PanelSectionRow>
            )}
          </>
        )}
        {exists && (
          <PanelSectionRow>
            <div style={{ color: "#4CAF50", fontSize: "13px" }}>✓ Lua script already installed</div>
          </PanelSectionRow>
        )}
        {updateStatus && (
          <PanelSectionRow>
            <Field label={updateStatus} />
          </PanelSectionRow>
        )}
      </PanelSection>

      {appid && (
        <PanelSection title="SLSsteam">
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={handleAddFakeId}>Add / Remove FakeAppId</ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={handleAddToken}>Add Token</ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={handleAddDlcs}>Add DLCs</ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={handleCheckUpdate}>Check Update</ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}
    </>
  );
};

export default AddGamePanel;
