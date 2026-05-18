import React, { FC, useState, useCallback } from "react";
import { callable } from "@decky/api";
import { ButtonItem, Field, PanelSection, TextField } from "@decky/ui";
import type { ApiResponse, FixEntry } from "../types/api";

const checkFixes = callable<[number], ApiResponse & { fixes: any[] }>("check_for_fixes");
const applyFix = callable<[number, string, string, string, string], ApiResponse>("apply_game_fix");
const getInstalled = callable<[], ApiResponse & { fixes: FixEntry[] }>("get_installed_fixes");
const unfix = callable<[number, string, string], ApiResponse>("unfix_game");

const FixesPanel: FC = () => {
  const [appid, setAppid] = useState("");
  const [fixes, setFixes] = useState<any[]>([]);
  const [installedFixes, setInstalledFixes] = useState<FixEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  const handleSearch = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    setLoading(true);
    setMsg("");
    const res = await checkFixes(id);
    if (res.success && res.fixes) setFixes(res.fixes);
    else setFixes([]);
    if (!res.success) setMsg(res.error || "No fixes found");
    const installed = await getInstalled();
    if (installed.success && installed.fixes) setInstalledFixes(installed.fixes);
    setLoading(false);
  }, [appid]);

  const handleApply = useCallback(async (fix: any) => {
    const id = parseInt(appid);
    if (!id) return;
    setMsg(`Applying fix for ${fix.game_name || appid}...`);
    const res = await applyFix(id, fix.download_url || "", fix.install_path || "", fix.fix_type || "", fix.game_name || "");
    setMsg(res.message || (res.success ? "Fix applied!" : res.error || ""));
    const installed = await getInstalled();
    if (installed.success && installed.fixes) setInstalledFixes(installed.fixes);
  }, [appid]);

  const handleUnfix = useCallback(async (fix: FixEntry) => {
    setMsg(`Removing fix for ${fix.gameName}...`);
    const res = await unfix(fix.appid, fix.installPath, fix.fixDate);
    setMsg(res.message || (res.success ? "Fix removed!" : res.error || ""));
    const installed = await getInstalled();
    if (installed.success && installed.fixes) setInstalledFixes(installed.fixes);
  }, []);

  return (
    <>
      <PanelSection title="Search Fixes">
        <TextField
          value={appid}
          onChange={(e) => setAppid(e.target.value)}
        />
        <ButtonItem layout="below" onClick={handleSearch} disabled={loading || !appid}>
          {loading ? "Searching..." : "Search"}
        </ButtonItem>
      </PanelSection>

      {fixes.length > 0 && (
        <PanelSection title="Available Fixes">
          {fixes.map((fix, i) => (
            <Field
              key={i}
              label={fix.game_name || fix.name || `Fix #${i + 1}`}
              description={fix.fix_type || fix.description || ""}
            >
              <ButtonItem layout="below" onClick={() => handleApply(fix)}>
                Apply
              </ButtonItem>
            </Field>
          ))}
        </PanelSection>
      )}

      {installedFixes.length > 0 && (
        <PanelSection title="Applied Fixes">
          {installedFixes.map((fix, i) => (
            <Field
              key={i}
              label={`${fix.gameName} (${fix.appid})`}
              description={`${fix.fixType} | ${fix.fixDate}`}
            >
              <ButtonItem layout="below" onClick={() => handleUnfix(fix)}>
                Remove Fix
              </ButtonItem>
            </Field>
          ))}
        </PanelSection>
      )}

      {msg && (
        <PanelSection title="Status">
          <div style={{ padding: "6px", fontSize: "13px" }}>{msg}</div>
        </PanelSection>
      )}
    </>
  );
};

export default FixesPanel;
