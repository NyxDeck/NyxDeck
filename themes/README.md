# 自定义主题

DMS 的自定义主题 JSON：在设置面板 **Theme & Colors → Custom** 里选文件导入，
或在 `settings.json` 里设：

```json
{
  "currentThemeName": "custom",
  "customThemeFile": "/home/youxi/NyxDeck/themes/xxx.json"
}
```

配色字段（`primary` / `surface` / `surfaceContainer` / `error` 等）见
`/usr/share/doc/dms-shell/CUSTOM_THEMES.md`。机器上还自带一批可直接用的：
`/usr/share/doc/dms-shell/theme_*.json`（Nord、Rose-Pine、Gruvbox、
Everforest、Synthwave、Tokyo Night 等）。

放这里的主题，用 `install.sh` 之外的软链或直接引用绝对路径都行——
主题 JSON 不经过 `~/.config`，`install.sh` 不管它。
