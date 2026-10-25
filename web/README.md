# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).

## 安卓端打包

在 `web` 目录下执行：

```bash
npm run build:mobile
npx cap sync android
```

然后用 Android Studio 打开 `web/android` 运行。每次修改前端代码后都需要重新执行这两条命令。
