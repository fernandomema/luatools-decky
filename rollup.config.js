import deckyPlugin from "@decky/rollup";

export default deckyPlugin({
  production: process.env.ROLLUP_ENV === "production",
});
