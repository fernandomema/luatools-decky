import React, { FC, useEffect, useCallback, useRef } from "react";
import { callable, fetchNoCors, toaster } from "@decky/api";

const startAdd = callable<[number], { success: boolean }>("start_add_via_luatools");
const getStatus = callable<[number], { success: boolean; state?: { status: string } }>("get_add_status");
const addToken = callable<[number], { success: boolean }>("add_game_token");
const addFakeId = callable<[number], { success: boolean }>("add_fake_app_id");
const addDlcs = callable<[number], { success: boolean }>("add_game_dlcs");
const getSlsStatus = callable<[], { success: boolean; installed: boolean; injected: { already_ok: boolean; patched: boolean; error?: string } }>("get_slssteam_status");
const restartSteam = callable<[], { success: boolean }>("restart_steam");

function extractAppid(url: string): number | null {
  const m = url.match(/\/app\/(\d+)/);
  if (m && m[1]) {
    const id = parseInt(m[1], 10);
    if (id > 0 && id < 9999999) return id;
  }
  return null;
}

let lastDetectedAppid = 0;

const InjectButton: FC = () => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const progressRef = useRef<NodeJS.Timeout | null>(null);

  const stopProgress = useCallback(() => {
    if (progressRef.current) {
      clearInterval(progressRef.current);
      progressRef.current = null;
    }
  }, []);

  const finishDownload = useCallback(async (appid: number) => {
    toaster.toast({ title: "LuaTools", body: "Adding Token, FakeAppId, DLCs..." });
    await addToken(appid);
    await addFakeId(appid);
    await addDlcs(appid);

    const sls = await getSlsStatus();
    if (!sls.installed) {
      toaster.toast({ title: "LuaTools", body: "SLSsteam not installed. Install it first.", duration: 8000 });
      return;
    }
    if (!sls.injected?.already_ok && !sls.injected?.patched) {
      toaster.toast({ title: "LuaTools", body: "Could not inject SLSsteam. Check SLSsteam tab.", duration: 8000 });
      return;
    }

    toaster.toast({ title: "LuaTools", body: "Restarting Steam...", duration: 3000 });
    await new Promise(r => setTimeout(r, 1500));
    const r = await restartSteam();
    if (!r.success) {
      toaster.toast({ title: "LuaTools", body: "Restart Steam manually from the QAM.", duration: 8000 });
    }
  }, []);

  const waitForDone = useCallback(async (appid: number) => {
    stopProgress();
    progressRef.current = setInterval(async () => {
      const s = await getStatus(appid);
      if (!s.state) return;
      if (s.state.status === "done") {
        stopProgress();
        finishDownload(appid);
      } else if (s.state.status === "failed") {
        stopProgress();
        toaster.toast({ title: "LuaTools", body: "Download failed. Try again.", duration: 5000 });
      }
    }, 2000);
  }, [stopProgress, finishDownload]);

  const handleDownload = useCallback(async (appid: number) => {
    const res = await startAdd(appid);
    if (res.success) waitForDone(appid);
  }, [waitForDone]);

  const checkTabs = useCallback(async () => {
    try {
      const resp: any = await fetchNoCors("http://127.0.0.1:8080/json");
      let tabs: any[] = [];
      if (resp?.result?.body) {
        const raw = JSON.parse(resp.result.body);
        if (Array.isArray(raw)) tabs = raw;
      } else if (typeof resp?.json === "function") {
        const arr = await resp.json();
        if (Array.isArray(arr)) tabs = arr;
      } else if (typeof resp?.text === "function") {
        const parsed = JSON.parse(await resp.text());
        if (Array.isArray(parsed)) tabs = parsed;
      }
      for (const tab of tabs) {
        const id = extractAppid(tab.url || "");
        if (id && id !== lastDetectedAppid) {
          lastDetectedAppid = id;
          try {
            // Save last visited appid in localStorage for the AddGame panel to pick up
            window.localStorage.setItem('luatools_lastVisitedAppid', String(id));
          } catch (e) {
            // fallback to toast if storage fails
            toaster.toast({ title: "LuaTools", body: `Download AppID ${id}?`, duration: 10000, onClick: () => handleDownload(id) });
          }
          return;
        }
      }
    } catch {}
  }, [handleDownload]);

  useEffect(() => {
    checkTabs();
    intervalRef.current = setInterval(checkTabs, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      stopProgress();
    };
  }, [checkTabs, stopProgress]);

  return null;
};

export default InjectButton;
