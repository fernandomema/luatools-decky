import { definePlugin, routerHook } from "@decky/api";
import React, { FC, useState, useCallback } from "react";
import { FaDownload } from "react-icons/fa";
import AddGamePanel from "./components/AddGamePanel";
import InstalledGamesPanel from "./components/InstalledGamesPanel";
import SLSsteamPanel from "./components/SLSsteamPanel";
import SettingsPanel from "./components/SettingsPanel";
import FixesPanel from "./components/FixesPanel";
import WorkshopPanel from "./components/WorkshopPanel";
import InjectButton from "./components/InjectButton";
import { Tabs } from "@decky/ui";

const TABS = [
  { value: "add", label: "Add Game" },
  { value: "installed", label: "Installed" },
  { value: "slssteam", label: "SLSsteam" },
  { value: "fixes", label: "Fixes" },
  { value: "workshop", label: "Workshop" },
  { value: "settings", label: "Settings" },
];

const TAB_KEY = "luatools_activeTab";

const Content: FC = () => {
  const [activeTab, setActiveTab] = useState<string>(() => {
    try { return sessionStorage.getItem(TAB_KEY) || "add"; } catch { return "add"; }
  });

  const handleShowTab = useCallback((tabID: string) => {
    setActiveTab(tabID);
    try { sessionStorage.setItem(TAB_KEY, tabID); } catch {}
  }, []);

  const tabs = [
    { title: "Add Game", content: <AddGamePanel />, id: "add" },
    { title: "Installed", content: <InstalledGamesPanel />, id: "installed" },
    { title: "Fixes", content: <FixesPanel />, id: "fixes" },
    { title: "Workshop", content: <WorkshopPanel />, id: "workshop" },
    { title: "SLSsteam", content: <SLSsteamPanel />, id: "slssteam" },
    { title: "Settings", content: <SettingsPanel />, id: "settings" },
  ];
  // Decky Tabs may render tab.content itself which can duplicate our manual rendering.
  // Create a header-only version to pass to Tabs so we control content rendering below.
  const tabsForHeaders = tabs.map(({ title, id }) => ({ title, id }));

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Header area for Tabs. Fixed height prevents Tabs from overlapping the content below. */}
      <div style={{ height: "48px", marginTop: "8px" }}>
        <Tabs
          activeTab={activeTab}
          onShowTab={(tabID: string) => handleShowTab(tabID)}
          tabs={tabsForHeaders}
        />
      </div>
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {activeTab === "add" && <AddGamePanel />}
        {activeTab === "installed" && <InstalledGamesPanel />}
        {activeTab === "fixes" && <FixesPanel />}
        {activeTab === "workshop" && <WorkshopPanel />}
        {activeTab === "slssteam" && <SLSsteamPanel />}
        {activeTab === "settings" && <SettingsPanel />}
      </div>
    </div>
  );
};

const INJECT_BUTTON_NAME = "luatools-inject-btn";

export default definePlugin(() => {
  routerHook.addGlobalComponent(INJECT_BUTTON_NAME, InjectButton);
  return {
    name: "LuaTools Decky",
    content: <Content />,
    icon: <FaDownload />,
    onDismount() {
      routerHook.removeGlobalComponent(INJECT_BUTTON_NAME);
    },
  };
});
