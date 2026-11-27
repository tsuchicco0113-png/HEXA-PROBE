// =====================================================================
//  HEXA STAGE  CPZ USB-C PWR + TEST ｷｬｯﾌﾟ v0.1
//  Cap LoRa-1262 と同じ「上面まるごと」の形 (84 x 24)。
//  中に USB-C PWR 基板 v0.2 と導通ﾁｪｯｸの配線 (G22 →1kΩ→ 赤 / GND → 黒) を収め、
//  右端からﾃｽﾄ線2本を出す (先に 4mm ﾊﾞﾅﾅのﾒｽ)。
//
//  座標は v0.2 ｶﾊﾞーと同じ: x = 本体を正面から見た左→右 (本体の左端 0)、
//  y = 背面からの奥行き (背面 0)、z = 本体上面から上。印刷は天面を下に (part="print")
// =====================================================================
part = "print";      // "print" / "fittest" (柱まわりだけの試し刷り) / "fit"
$fn = 48;
eps = 0.01;

// ---- 本体
BW = 84.0;            // 幅
BD = 22.1;            // 厚み (ｷｰ除く)
// ---- 基板 (v0.2)
bx  = 31.0;           // 基板の左端 (14P 中心 x=42)
PW  = 22.0;  PD = 17.6;
hdr_h = 2.5;  pcb_t = 1.6;  usb_h = 3.26;
usb_x = bx + 11.0;  usb_y0 = -0.3;              // USB-C の口は背面から 0.3 出る
lego  = [[bx + 3, 4], [bx + 19, 4]];            // 上面の LEGO 穴 (x34/50, 背面から4)
led   = [bx + 7.2, 16.45];
// ---- 基板の押さえ
press = 0.3;          // 柱が基板を押し下げる量 (mm)。ｶﾀつく→増やす / ｷｬｯﾌﾟが入りきらない→減らす (0〜0.5)
// ---- ｷｬｯﾌﾟ
wall = 1.6;  roof = 1.6;
inner_h = hdr_h + pcb_t + usb_h + 1.0;          // 中の高さ (線と抵抗の分 +0.6)
H  = inner_h + roof;                            // 約 10mm (Cap LoRa は 15.2)
y0 = usb_y0 - 0.2 - wall;                       // 背面側は USB-C の口の分だけ出す
y1 = BD;                                        // 正面は本体と面一
r_side = 3.0;  r_top = 2.0;
// ---- ﾃｽﾄ線 (右端から)
wire_d  = 3.2;                                  // ﾃｽﾄ線の外径 + 余裕 (AWG22〜20 想定)
wires   = [[15.0, "Ω"], [6.0, "COM"]];          // [y, 刻印]  正面寄り=赤(G22) / 背面寄り=黒(GND)
wire_z  = 3.6;
// ---- 背面の耳 (M2 ﾈｼﾞ、Cap LoRa と同じ止め方。不要なら false)
use_ears = true;
ears_x   = [28, 56];                            // 背面上端ｽﾄﾘｯﾌﾟの M2 (左右対称)
ear_h    = 6.0;                                 // 上面から下へ
ear_z    = -3.1;                                // 穴の中心 (ｽﾄﾘｯﾌﾟ 6.2 の真ん中、要実測)
// ---- 上面の穴を避けたい所 (microSD など)。[[x0, x1, y0, y1], ...] で切り欠く
keepout = [];

module rounded_block(x0, x1, ya, yb, h) {
  // 縦の角 r_side、天面の縁 r_top で丸めた箱 (底は平ら)
  hull() for (x = [x0 + r_side, x1 - r_side], y = [ya + r_side, yb - r_side]) translate([x, y, 0]) {
    cylinder(r = r_side, h = h - r_top);
    translate([0, 0, h - r_top]) scale([1, 1, r_top / r_side]) sphere(r = r_side);
  }
}

module peg() {       // LEGO 穴に入る割りﾋﾟﾝ (v0.2 ｶﾊﾞーと同じ)
  peg_d = 4.75;  peg_in = 3.5;
  L = hdr_h + pcb_t + peg_in;
  difference() {
    union() {
      translate([0, 0, -L + 0.6]) cylinder(d = peg_d, h = L - 0.6 + eps);
      translate([0, 0, -L]) cylinder(d1 = peg_d - 0.8, d2 = peg_d, h = 0.6);
    }
    translate([-0.4, -4, -L - 1]) cube([0.8, 8, peg_in + 1]);
  }
}

module ear(x) {
  w = 8;
  difference() {
    hull() {
      translate([x - w/2, y0, -0.01]) cube([w, wall, 0.01]);
      translate([x, y0 + wall, -ear_h + w/2]) rotate([90, 0, 0]) cylinder(d = w, h = wall);
    }
    translate([x, y0 - 1, ear_z]) rotate([-90, 0, 0]) cylinder(d = 2.3, h = wall + 2);
  }
}

module shell() {
  difference() {
    rounded_block(0, BW, y0, y1, H);
    // 中 (底から inner_h まで)
    translate([wall, y0 + wall, -eps]) cube([BW - 2*wall, y1 - y0 - 2*wall, inner_h + eps]);
    // USB-C の口 (ﾌﾟﾗｸﾞの太い所も入るように)
    translate([usb_x, y0 - eps, hdr_h + pcb_t + usb_h/2]) rotate([-90, 0, 0])
      linear_extrude(wall + 1) offset(r = 2) square([12.6 - 4, 7.0 - 4], center = true);
    // LED の窓 (天面)
    translate([led[0], led[1], inner_h - eps]) cylinder(d = 2.2, h = roof + 1);
    // ﾃｽﾄ線の出口 (右端) と刻印 (右端の面、上下は印刷向きで読める向き)
    for (w = wires) {
      translate([BW - wall - 1, w[0], wire_z]) rotate([0, 90, 0]) cylinder(d = wire_d, h = wall + 2);
      translate([BW - 0.4, w[0], wire_z + 2.1]) rotate([90, 0, 90])
        linear_extrude(1) mirror([1, 0, 0])
          text(w[1], size = 2.1, halign = "center", valign = "bottom", font = "Liberation Sans:style=Bold");
    }
    // 正面の細い溝 (Cap 風のﾗｲﾝ)
    translate([6, y1 - 0.45, H * 0.45]) cube([BW - 12, 1, 0.6]);
    for (k = keepout) translate([k[0], k[2], -eps]) cube([k[1] - k[0], k[3] - k[2], H + 1]);
  }
}

module inside() {
  // 基板を押さえる柱 + LEGO ﾋﾟﾝ
  for (p = lego) translate([p[0], p[1], 0]) {
    zb = hdr_h + pcb_t - press;                     // 柱の下面 (基板の上面より press だけ下)
    translate([0, 0, zb]) cylinder(d = 6.0, h = inner_h - zb + eps);
    translate([0, 0, hdr_h + pcb_t]) peg();         // ﾋﾟﾝ先の位置は変えない
  }
  // 線の抜け止め: 出口の手前に柱を千鳥に (線を S 字に通す)
  for (p = [[BW - 7, 10.5], [BW - 11, 3.5], [BW - 11, 17.5]])
    translate([p[0], p[1], 1.2]) cylinder(d = 2.6, h = inner_h - 1.2 + eps);
  // 1kΩ と熱収縮の置き場の仕切り (低い壁、基板と配線を分ける)
  translate([bx + PW + 2.5, y0 + wall, inner_h - 3.0]) cube([1.2, 5.5, 3.0 + eps]);
}

module cap() {
  shell();
  inside();
  if (use_ears) for (x = ears_x) ear(x);
}

module dummy() {
  color("dimgray") translate([0, 0, -12]) cube([BW, BD, 12]);                     // 本体の上の方
  color("green") translate([bx, 0, hdr_h]) cube([PW, PD, pcb_t]);
  color("silver") translate([usb_x - 4.47, usb_y0, hdr_h + pcb_t]) cube([8.94, 7.3, usb_h]);
  color("black") translate([bx + 2, 12.03 - 1.4, 0]) cube([18, 5.3, hdr_h]);
  // ﾃｽﾄ線と抵抗
  color("red")   translate([bx + 13.54, 14.57, hdr_h + pcb_t]) cylinder(d = 1.6, h = 2);
  color("tan")   translate([bx + PW + 5, 14.5, 4.2]) rotate([0, 90, 0]) cylinder(d = 2.4, h = 6.5);
  color("red")   translate([BW - 14, 15, wire_z]) rotate([0, 90, 0]) cylinder(d = 2.4, h = 20);
  color("black") translate([BW - 14, 6, wire_z]) rotate([0, 90, 0]) cylinder(d = 2.4, h = 20);
}

module fittest() {
  // 柱2本とﾋﾟﾝ、それをつなぐ天板だけ (約10分)。本体に挿して基板のｶﾀつきを確かめる
  intersection() {
    cap();
    translate([lego[0][0] - 5, y0 - 1, -20]) cube([lego[1][0] - lego[0][0] + 10, 11 - y0, 40]);
  }
}

if (part == "print") translate([0, 0, H]) mirror([0, 0, 1]) cap();   // 天面を下に (ｻﾎﾟｰﾄ不要)
else if (part == "fittest") translate([0, 0, H]) mirror([0, 0, 1]) fittest();
else if (part == "fit") { dummy(); color("whitesmoke", 0.85) cap(); }
else { color("whitesmoke") cap(); }
