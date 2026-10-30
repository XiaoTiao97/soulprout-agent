// tauri 构建时要求 bundle.resources 里声明的目录存在且非空。开发模式（debug）虽然直接用本机 Python 起 sidecar，
// 也会做这个检查。这里在目录缺失时放一个占位文件；真正打包时 scripts/build.ps1 会先清空目录，再放入 PyInstaller 的产物。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const bundleDir = path.resolve(here, '../src-tauri/sidecar-bundle')

if (!fs.existsSync(bundleDir) || fs.readdirSync(bundleDir).length === 0) {
  fs.mkdirSync(bundleDir, { recursive: true })
  const file = path.join(bundleDir, 'PLACEHOLDER.txt')
  fs.writeFileSync(file, 'dev placeholder; replaced by scripts/build.ps1 with the PyInstaller output.\n')
  console.log(`[desktop] created sidecar placeholder: ${file}`)
}
