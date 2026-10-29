// tauri 构建时要求 externalBin 对应的文件存在，开发模式（debug）虽然直接用本机 Python 起 sidecar，
// 也会做这个检查。这里在文件缺失时放一个空占位文件；真正打包时 scripts/build.ps1 会用 PyInstaller 的产物覆盖它。
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const binDir = path.resolve(here, '../src-tauri/binaries')

let triple = 'x86_64-pc-windows-msvc'
try {
  const out = execSync('rustc -vV', { encoding: 'utf8' })
  const match = out.match(/^host:\s*(.+)$/m)
  if (match) triple = match[1].trim()
} catch {
  /* 没有 rustc 就用默认值 */
}

const file = path.join(binDir, `soulprout-desktop-sidecar-${triple}${triple.includes('windows') ? '.exe' : ''}`)
if (!fs.existsSync(file)) {
  fs.mkdirSync(binDir, { recursive: true })
  fs.writeFileSync(file, '')
  console.log(`[desktop] created sidecar placeholder: ${file}`)
}
