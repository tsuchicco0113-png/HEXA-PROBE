// =====================================================================
//  HEXA STAGE  CPZ ﾄﾞｯｸ v0.1 — USB-C PWR ｷｬｯﾌﾟ (v0.6) ＋ 背面ﾊﾞｯﾃﾘｰﾄﾚｲ の一体型
//  - 本体の上に基板のｷｬｯﾌﾟ、背面に CIO SMARTCOBY SLIM 5000mAh。横から見て「T」の字
//  - 付け方: 真上から差す (ﾍｯﾀﾞｰが 14P、LEGO ﾋﾟﾝが穴、背面の板が背面に沿って下りる)
//    → 背面から M2×4 を最大4本 (上端の穴 x28/x56 ＋ 背面のｲﾝｻｰﾄ2か所、どれも床の皿もみから)
//  - ｷｬｯﾌﾟの USB-C からﾊﾞｯﾃﾘｰへは、ﾎﾟｹｯﾄの上の「通り道」に短い L字 C-C ｹｰﾌﾞﾙを通す
//    (差し込み口の側が開いている)
//  - 中身は ../cap と ../battery-sled の scad をそのまま使う (寸法はそちらで合わせる)
//
//  座標: ﾄﾚｲと同じ (背面を正面に見て u 左→右 / v 下→上 (本体の下端 0) / w 背面から外へ)
//  印刷は part="print": 差し込み口の反対の端を下に立てる (ﾎﾟｹｯﾄと通り道は縦に抜ける)。
//  ｷｬｯﾌﾟの下の端だけ浮くので、そこだけ「ﾍﾞｯﾄﾞからのｻﾎﾟｰﾄ」を付ける
// =====================================================================
use <../cap/hexa_cpz_probe_cap.scad>
use <../battery-sled/hexa_cpz_battery_sled.scad>

part      = "print";     // "print" / "model" / "fit" (fit は ../cap/body.stl が要る)
open_end  = "right";     // ﾊﾞｯﾃﾘｰの差し込み口 (背面から見て) "right" / "left"
use_jacks = true;        // false = ﾊﾞﾅﾅｼﾞｬｯｸの穴なし
eps = 0.01;

BW = 84;  BH = 54;
// ｷｬｯﾌﾟ座標 (x 正面から見て左→右 / y 背面から / z 上面から) → ﾄﾚｲ座標
M = [[-1, 0, 0, BW], [0, 0, 1, BH], [0, -1, 0, 0], [0, 0, 0, 1]];

// ﾄﾚｲ・ｷｬｯﾌﾟの寸法 (それぞれの scad と同じ値)
fit = 0.4;  wall = 1.6;  PL = 88.0 + 2*fit;
ou0 = BW/2 - PL/2 - wall;  ou1 = BW/2 + PL/2 + wall;
cap_x = [5.8, 78.2];  cap_in = [7.8, 76.2];  cap_h = 15.2;  cap_roof = 1.6;

module dock() {
  difference() {
    union() {
      tray(dock = true, oe = open_end);
      multmatrix(M) cap(sk = 0, jk = use_jacks);
    }
    // ｷｬｯﾌﾟの中 (本体背面より前) にﾄﾚｲの床がはみ出さないように
    translate([BW - cap_in[1], BH - eps, -0.6]) cube([cap_in[1] - cap_in[0], cap_h - cap_roof, 1.1]);
    // USB-C の口をﾄﾚｲの壁ごと抜く (ﾌﾟﾗｸﾞが入る)
    multmatrix(M) usb_cut(extra = 12);
  }
}

module body() {
  multmatrix(M) multmatrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, -59], [0, 0, 0, 1]]) import("../cap/body.stl");
}

if (part == "view") rotate([90, 0, 0]) { color([0.42, 0.44, 0.48]) body(); color("whitesmoke") dock(); }
else if (part == "print") {
  // 閉じた端を下に: right → u の小さい端 (ou0) が下
  if (open_end == "right") multmatrix([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, -ou0], [0, 0, 0, 1]]) dock();
  else                     multmatrix([[0, 1, 0, 0], [0, 0, -1, 0], [-1, 0, 0, ou1], [0, 0, 0, 1]]) dock();
}
else if (part == "fit") { color([0.5, 0.52, 0.56]) body(); color("whitesmoke") dock(); }
else dock();
