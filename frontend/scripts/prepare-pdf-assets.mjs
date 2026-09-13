import { cp, mkdir, readFile, stat } from "node:fs/promises";

// PDF.js 的中文字型對照、標準字型與圖片解碼器必須與套件版本一致。
const source = new URL("../node_modules/pdfjs-dist/", import.meta.url);
const target = new URL("../public/pdfjs/", import.meta.url);
await mkdir(target, { recursive: true });
for (const directory of ["cmaps", "standard_fonts", "wasm"]) {
  await cp(new URL(directory, source), new URL(directory, target), {
    recursive: true,
    // 避免重寫相同資源觸發開發頁面重載，保留正在編輯的對話草稿。
    filter: async (from, to) => {
      if ((await stat(from)).isDirectory()) return true;
      try { return !(await readFile(from)).equals(await readFile(to)); }
      catch (error) { if (error.code === "ENOENT") return true; throw error; }
    },
  });
}
