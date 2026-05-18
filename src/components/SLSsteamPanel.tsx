import React, { FC, useState, useCallback, useEffect } from "react";
import { callable } from "@decky/api";
import {
  PanelSection,
  PanelSectionRow,
  ButtonItem,
  ToggleField,
  Field,
  TextField,
} from "@decky/ui";
import type { ApiResponse, SLSStatus } from "../types/api";

const getPlayStatus = callable<[], ApiResponse & { enabled: boolean }>("get_sls_play_status");
const setPlayStatus = callable<[boolean], ApiResponse>("set_sls_play_status");
const getSlsStatus = callable<[], ApiResponse & SLSStatus>("get_slssteam_status");
const addFakeId = callable<[number], ApiResponse>("add_fake_app_id");
const removeFakeId = callable<[number], ApiResponse>("remove_fake_app_id");
const checkFakeId = callable<[number], ApiResponse & { exists: boolean }>("check_fake_app_id_status");
const addToken = callable<[number], ApiResponse>("add_game_token");
const removeToken = callable<[number], ApiResponse>("remove_game_token");
const checkToken = callable<[number], ApiResponse & { exists: boolean }>("check_game_token_status");
const addDlcs = callable<[number], ApiResponse>("add_game_dlcs");
const removeDlcs = callable<[number], ApiResponse>("remove_game_dlcs");
const checkDlcs = callable<[number], ApiResponse & { exists: boolean }>("check_game_dlcs_status");

const SLSsteamPanel: FC = () => {
  const [playEnabled, setPlayEnabled] = useState(false);
  const [slsInfo, setSlsInfo] = useState<SLSStatus | null>(null);
  const [appid, setAppid] = useState("");
  const [actionMsg, setActionMsg] = useState("");
  const [fakeIdExists, setFakeIdExists] = useState<boolean | null>(null);
  const [tokenExists, setTokenExists] = useState<boolean | null>(null);
  const [dlcExists, setDlcExists] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    const play = await getPlayStatus();
    if (play.success) setPlayEnabled(play.enabled ?? false);
    const info = await getSlsStatus();
    if (info.success) setSlsInfo(info);
  }, []);

  useEffect(() => { load(); }, [load]);

  const togglePlay = useCallback(async () => {
    const newVal = !playEnabled;
    const res = await setPlayStatus(newVal);
    if (res.success) setPlayEnabled(newVal);
    setActionMsg(res.message || (res.success ? "Updated!" : res.error || ""));
  }, [playEnabled]);

  const handleCheckAll = useCallback(async () => {
    const id = parseInt(appid);
    if (!id) return;
    setActionMsg("Checking...");
    const f = await checkFakeId(id);
    setFakeIdExists(f.exists ?? false);
    const t = await checkToken(id);
    setTokenExists(t.exists ?? false);
    const d = await checkDlcs(id);
    setDlcExists(d.exists ?? false);
    setActionMsg("Check complete");
  }, [appid]);

  const handleAdd = useCallback(async (action: string) => {
    const id = parseInt(appid);
    if (!id) return;
    let res: ApiResponse;
    if (action === "fakeid") res = await addFakeId(id);
    else if (action === "token") res = await addToken(id);
    else res = await addDlcs(id);
    setActionMsg(res.message || res.error || "");
    handleCheckAll();
  }, [appid, handleCheckAll]);

  const handleRemove = useCallback(async (action: string) => {
    const id = parseInt(appid);
    if (!id) return;
    let res: ApiResponse;
    if (action === "fakeid") res = await removeFakeId(id);
    else if (action === "token") res = await removeToken(id);
    else res = await removeDlcs(id);
    setActionMsg(res.message || res.error || "");
    handleCheckAll();
  }, [appid, handleCheckAll]);

  return (
    <>
      <PanelSection title="Engine">
        {slsInfo && (
          <PanelSectionRow>
            <Field label="Estado" childrenLayout="below">
              <div style={{ fontSize: "12px", color: "#aaa" }}>
                Instalado: {slsInfo.installed ? "✓" : "✗"} | Inyectado: {slsInfo.injected?.already_ok ? "✓" : slsInfo.injected?.patched ? "Patched" : "✗"}
              </div>
            </Field>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ToggleField
            label="Play Not Owned Games"
            checked={playEnabled}
            onChange={togglePlay}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="App Actions">
        <PanelSectionRow>
          <TextField
            label="AppID"
            value={appid}
            onChange={(e) => {
              setAppid(e.target.value);
              setFakeIdExists(null);
              setTokenExists(null);
              setDlcExists(null);
              setActionMsg("");
            }}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" bottomSeparator="none" onClick={handleCheckAll} disabled={!appid}>
            Check Status
          </ButtonItem>
        </PanelSectionRow>

        {fakeIdExists !== null && (
          <>
            <PanelSectionRow>
              <Field label={`FakeAppId: ${fakeIdExists ? "✓ instalado" : "✗ no instalado"}`} childrenLayout="below">
                <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleAdd("fakeid")} disabled={!appid}>
                    Add
                  </ButtonItem>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleRemove("fakeid")} disabled={!appid}>
                    Remove
                  </ButtonItem>
                </div>
              </Field>
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label={`Token: ${tokenExists ? "✓ instalado" : "✗ no instalado"}`} childrenLayout="below">
                <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleAdd("token")} disabled={!appid}>
                    Add
                  </ButtonItem>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleRemove("token")} disabled={!appid}>
                    Remove
                  </ButtonItem>
                </div>
              </Field>
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label={`DLCs: ${dlcExists ? "✓ instalados" : "✗ no instalados"}`} childrenLayout="below">
                <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleAdd("dlcs")} disabled={!appid}>
                    Add
                  </ButtonItem>
                  <ButtonItem layout="below" bottomSeparator="none" onClick={() => handleRemove("dlcs")} disabled={!appid}>
                    Remove
                  </ButtonItem>
                </div>
              </Field>
            </PanelSectionRow>
          </>
        )}

        {actionMsg && (
          <PanelSectionRow>
            <Field label={actionMsg} />
          </PanelSectionRow>
        )}
      </PanelSection>
    </>
  );
};

export default SLSsteamPanel;
