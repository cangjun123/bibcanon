/**
 * Copy text to clipboard reliably on both HTTPS/localhost AND plain HTTP public cloud IPs.
 */
export async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  // Fallback for plain HTTP cloud servers (`http://<server-ip>:8765`)
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    const ok = document.execCommand("copy");
    if (!ok) {
      throw new Error("浏览器拒绝写入剪贴板，请使用右侧“下载 .bib 文件”");
    }
  } finally {
    document.body.removeChild(textarea);
  }
}
