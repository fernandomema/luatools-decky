export interface ApiResponse<T = any> {
  success: boolean;
  error?: string;
  message?: string;
  [key: string]: T | boolean | string | undefined;
}

export interface DownloadState {
  status: string;
  currentApi?: string;
  bytesRead?: number;
  totalBytes?: number;
  error?: string;
  api?: string;
  installedPath?: string;
  progress?: number;
  message?: string;
  percent?: number;
}

export interface InstalledScript {
  appid: number;
  gameName: string;
  filename: string;
  isDisabled: boolean;
  fileSize: number;
  modifiedDate: string;
  path: string;
}

export interface FixEntry {
  appid: number;
  gameName: string;
  fixDate: string;
  installPath: string;
  fixType: string;
  downloadUrl: string;
  status: string;
}

export interface SLSStatus {
  installed: boolean;
  injected: { patched: boolean; already_ok: boolean; error: string | null };
  config_exists: boolean;
}

export interface SteamLibrary {
  path: string;
  label: string;
  free: number;
}

export interface GamesDBEntry {
  name: string;
  playable: number;
  denuvo: boolean;
  "of-available": boolean;
}
