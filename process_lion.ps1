# ============================================================
#  process_lion.ps1
#  Re-cut lion_crop.png from the source lion image
#    (2048x2048, near-white background).
#  Steps:
#    1) Color-tolerance flood-fill from the 4 borders to mark the
#       *exterior* background only. Interior light highlights
#       surrounded by darker fur are kept (never reached).
#    2) Enclosed holes (not connected to the border) stay opaque
#       (= "fill missing"), keeping their original color.
#    3) Erode the foreground by N px to remove the white/blend fringe.
#    4) Crop to fg bbox + padding. Output a hard matte (alpha 0/255),
#       transparent pixels zeroed to black so runtime bicubic
#       interpolation cannot produce purple/magenta edges.
# ============================================================
Add-Type -AssemblyName System.Drawing
$here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$katong = Join-Path $here 'katong'

$pngs = Get-ChildItem -LiteralPath $katong -Filter *.png
$src = $pngs | Where-Object { $_.Name -ne 'lion_crop.png' -and $_.Name -ne 'deskpet-lion-3d.png' } |
       Sort-Object Length -Descending | Select-Object -First 1
if (-not $src) { throw "lion source image not found" }
$srcPath = $src.FullName
$dstPath = Join-Path $katong 'lion_crop.png'

$csharp = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;

public static class LionCutout
{
    public static string Run(string src, string dst, double tol, int erode, int pad)
    {
        using (Bitmap bmp0 = new Bitmap(src))
        {
            int w = bmp0.Width, h = bmp0.Height;
            // Unify to 32bppArgb (straight alpha) for byte-level access.
            Bitmap b32 = new Bitmap(w, h, PixelFormat.Format32bppArgb);
            using (Graphics g0 = Graphics.FromImage(b32))
            {
                g0.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                g0.DrawImage(bmp0, 0, 0, w, h);
            }

            Rectangle rect = new Rectangle(0, 0, w, h);
            BitmapData bd = b32.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            byte[] px = new byte[w * h * 4];
            Marshal.Copy(bd.Scan0, px, 0, px.Length);
            b32.UnlockBits(bd);
            b32.Dispose();

            // Background color = average of border pixels.
            // Memory layout is BGRA: px[o]=B, px[o+1]=G, px[o+2]=R, px[o+3]=A.
            long sr = 0, sg = 0, sb = 0; int n = 0;
            for (int x = 0; x < w; x += 7) { AddP(px, x, 0, w, ref sr, ref sg, ref sb, ref n); AddP(px, x, h - 1, w, ref sr, ref sg, ref sb, ref n); }
            for (int y = 0; y < h; y += 7) { AddP(px, 0, y, w, ref sr, ref sg, ref sb, ref n); AddP(px, w - 1, y, w, ref sr, ref sg, ref sb, ref n); }
            int br = (int)(sr / n), bg = (int)(sg / n), bb = (int)(sb / n);

            // Flood-fill from all border pixels: mark isBg where within tol of bg color.
            bool[] isBg = new bool[w * h];
            int[] queue = new int[w * h];
            int qh = 0, qt = 0;
            for (int x = 0; x < w; x++) { Seed(px, x, 0, w, br, bg, bb, tol, isBg, queue, ref qt); Seed(px, x, h - 1, w, br, bg, bb, tol, isBg, queue, ref qt); }
            for (int y = 0; y < h; y++) { Seed(px, 0, y, w, br, bg, bb, tol, isBg, queue, ref qt); Seed(px, w - 1, y, w, br, bg, bb, tol, isBg, queue, ref qt); }
            int[] dx = { 1, -1, 0, 0 };
            int[] dy = { 0, 0, 1, -1 };
            while (qh < qt)
            {
                int p = queue[qh++];
                int x = p % w, y = p / w;
                for (int k = 0; k < 4; k++)
                {
                    int nx = x + dx[k], ny = y + dy[k];
                    if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
                    int np = ny * w + nx;
                    if (isBg[np]) continue;
                    int o = np * 4;
                    int dr = px[o + 2] - br, dg = px[o + 1] - bg, db = px[o] - bb;
                    if (dr * dr + dg * dg + db * db <= tol * tol)
                    {
                        isBg[np] = true;
                        queue[qt++] = np;
                    }
                }
            }

            // Erode foreground by `erode` px (8-neighborhood) to strip the fringe.
            for (int e = 0; e < erode; e++)
            {
                bool[] nb = (bool[])isBg.Clone();
                for (int y = 0; y < h; y++)
                    for (int x = 0; x < w; x++)
                    {
                        int p = y * w + x;
                        if (isBg[p]) continue;
                        bool near = false;
                        for (int yy = -1; yy <= 1 && !near; yy++)
                            for (int xx = -1; xx <= 1; xx++)
                            {
                                if (xx == 0 && yy == 0) continue;
                                int nx = x + xx, ny = y + yy;
                                if (nx < 0 || ny < 0 || nx >= w || ny >= h) { near = true; break; }
                                if (isBg[ny * w + nx]) { near = true; break; }
                            }
                        if (near) nb[p] = true;
                    }
                isBg = nb;
            }

            // Foreground bounding box.
            int minX = int.MaxValue, minY = int.MaxValue, maxX = -1, maxY = -1;
            long fgCnt = 0;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    if (!isBg[y * w + x])
                    {
                        fgCnt++;
                        if (x < minX) minX = x; if (x > maxX) maxX = x;
                        if (y < minY) minY = y; if (y > maxY) maxY = y;
                    }
            if (maxX < 0) return "NO_FG";
            minX = Math.Max(0, minX - pad); minY = Math.Max(0, minY - pad);
            maxX = Math.Min(w - 1, maxX + pad); maxY = Math.Min(h - 1, maxY + pad);
            int ow = maxX - minX + 1, oh = maxY - minY + 1;

            // Output: hard matte, transparent=black, foreground keeps color alpha=255.
            using (Bitmap outBmp = new Bitmap(ow, oh, PixelFormat.Format32bppArgb))
            {
                BitmapData obd = outBmp.LockBits(new Rectangle(0, 0, ow, oh), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                byte[] outPx = new byte[ow * oh * 4];
                int magentaHits = 0;
                for (int y = 0; y < oh; y++)
                {
                    int srcY = minY + y;
                    for (int x = 0; x < ow; x++)
                    {
                        int srcX = minX + x;
                        int sp = (srcY * w + srcX) * 4;
                        int op = (y * ow + x) * 4;
                        if (isBg[srcY * w + srcX])
                        {
                            outPx[op] = 0; outPx[op + 1] = 0; outPx[op + 2] = 0; outPx[op + 3] = 0;
                        }
                        else
                        {
                            byte B = px[sp], G = px[sp + 1], R = px[sp + 2];
                            outPx[op] = B; outPx[op + 1] = G; outPx[op + 2] = R; outPx[op + 3] = 255;
                            // Detect foreground colors colliding with the transparency key (magenta 255,0,255).
                            if (Math.Abs(R - 255) < 6 && G < 10 && Math.Abs(B - 255) < 6) magentaHits++;
                        }
                    }
                }
                Marshal.Copy(outPx, 0, obd.Scan0, outPx.Length);
                outBmp.UnlockBits(obd);
                outBmp.Save(dst, ImageFormat.Png);
                long total = (long)w * h;
                StringBuilder rep = new StringBuilder();
                rep.AppendLine("src=" + w + "x" + h + "  bg=(" + br + "," + bg + "," + bb + ")  tol=" + tol + " erode=" + erode + " pad=" + pad);
                rep.AppendLine("fgPx=" + fgCnt + " (" + (100.0 * fgCnt / total).ToString("0.0") + "%)  bbox=(" + minX + "," + minY + ")-(" + maxX + "," + maxY + ")");
                rep.AppendLine("out=" + ow + "x" + oh + "  magentaHits=" + magentaHits);
                return rep.ToString();
            }
        }
    }

    private static void AddP(byte[] px, int x, int y, int w, ref long sr, ref long sg, ref long sb, ref int n)
    { int o = (y * w + x) * 4; sr += px[o + 2]; sg += px[o + 1]; sb += px[o]; n++; }

    private static void Seed(byte[] px, int x, int y, int w, int br, int bg, int bb, double tol, bool[] isBg, int[] queue, ref int qt)
    {
        int p = y * w + x;
        if (isBg[p]) return;
        int o = p * 4;
        int dr = px[o + 2] - br, dg = px[o + 1] - bg, db = px[o] - bb;
        if (dr * dr + dg * dg + db * db <= tol * tol) { isBg[p] = true; queue[qt++] = p; }
    }
}
'@
Add-Type -TypeDefinition $csharp -ReferencedAssemblies System.Drawing

if (Test-Path $dstPath) {
    $bak = Join-Path $katong 'lion_crop.bak.png'
    Copy-Item -LiteralPath $dstPath -Destination $bak -Force
    Write-Host ("backed up -> " + $bak)
}

$tol = 45.0; $erode = 2; $pad = 16
if ($args.Count -ge 1) { $tol = [double]$args[0] }
if ($args.Count -ge 2) { $erode = [int]$args[1] }
if ($args.Count -ge 3) { $pad = [int]$args[2] }

$report = [LionCutout]::Run($srcPath, $dstPath, $tol, $erode, $pad)
Write-Host $report
Write-Host ("saved -> " + $dstPath)
