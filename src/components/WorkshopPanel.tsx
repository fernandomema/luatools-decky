import React, { FC, useState, useCallback, useEffect, useRef } from "react";
import { callable } from "@decky/api";
import { ButtonItem, Field, PanelSection, TextField } from "@decky/ui";
import type { ApiResponse } from "../types/api";

const startDownload = callable<[number, number], ApiResponse>("start_workshop_download");
const getStatus = callable<[], ApiResponse & { status: string; progress: number; message: string }>("get_workshop_download_status");
const cancelDownload = callable<[], ApiResponse>("cancel_workshop_download");

const WorkshopPanel: FC = () => {
  const [appid, setAppid] = useState("");
  const [pubfileId, setPubfileId] = useState("");
  const [dlStatus, setDlStatus] = useState<{ status: string; progress: number; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const handleStart = useCallback(async () => {
    const aid = parseInt(appid);
    const pid = parseInt(pubfileId);
    if (!aid || !pid) return;
    setLoading(true);
    const res = await startDownload(aid, pid);
    if (res.success) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(async () => {
        const s = await getStatus();
        setDlStatus(s);
        if (s.status === "done" || s.status === "failed" || s.status === "cancelled") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          setLoading(false);
        }
      }, 1000);
    } else {
      setLoading(false);
    }
  }, [appid, pubfileId]);

  const handleCancel = useCallback(async () => {
    await cancelDownload();
    if (intervalRef.current) clearInterval(intervalRef.current);
    setLoading(false);
  }, []);

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  return (
    <>
      <PanelSection title="Workshop Downloader">
        <Field label="AppID">
          <TextField
            value={appid}
            onChange={(e) => setAppid(e.target.value)}
          />
        </Field>
        <Field label="PublishedFileID">
          <TextField
            value={pubfileId}
            onChange={(e) => setPubfileId(e.target.value)}
          />
        </Field>
        <ButtonItem layout="below" onClick={handleStart} disabled={loading || !appid || !pubfileId}>
          {loading ? "Downloading..." : "Download"}
        </ButtonItem>
        {loading && (
          <ButtonItem layout="below" onClick={handleCancel}>
            Cancel
          </ButtonItem>
        )}
      </PanelSection>

      {dlStatus && (
        <PanelSection title="Status">
          <Field label="State" description={dlStatus.message || undefined}>
            <span style={{ fontSize: "13px" }}>{dlStatus.status}</span>
          </Field>
          {dlStatus.status === "downloading" && (
            <Field label={`${dlStatus.progress.toFixed(1)}%`}>
              <div style={{ background: "#333", borderRadius: "4px", height: "8px", width: "100%" }}>
                <div style={{
                  background: "#1a9fff", borderRadius: "4px", height: "100%",
                  width: `${Math.min(100, dlStatus.progress)}%`,
                }} />
              </div>
            </Field>
          )}
        </PanelSection>
      )}
    </>
  );
};

export default WorkshopPanel;
