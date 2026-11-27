// =====================================================================
//  HEXA STAGE  CPZ USB-C PWR + TEST ｷｬｯﾌﾟ v0.2  (ﾊﾞﾅﾅｼﾞｬｯｸ MK-628 を左右に)
//  Cap LoRa-1262 と同じ「上面まるごと」の形と高さ (84 x 24 x 15.2)。
//  中に USB-C PWR 基板 v0.2 を収め、4mm ﾊﾞﾅﾅｼﾞｬｯｸを左右の端に1つずつ:
//    左 = COM (黒, GND)   右 = Ω (赤, G22 →1kΩ→ ｼﾞｬｯｸ。1kΩ はｼﾞｬｯｸの端子に直付け)
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
H  = 15.2;                                      // Cap LoRa-1262 と同じ高さ
inner_h = H - roof;                             // 中の高さ (ﾅｯﾄを回す余裕)
y0 = usb_y0 - 0.2 - wall;                       // 背面側は USB-C の口の分だけ出す
y1 = BD;                                        // 正面は本体と面一
r_side = 3.0;  r_top = 2.0;
// ---- 4mm ﾊﾞﾅﾅｼﾞｬｯｸ 秋月 MK-628-0 (赤) / MK-628-1 (黒)
use_jacks   = true;                             // false = 穴なし (USB 給電だけで使う時。刻印も消える)
//      秋月の表記: 取付穴 9mm、径 10.5mm、長さ 25.7mm。つばの厚み・ﾅｯﾄの大きさは未確認 (現物で確認)
jack_hole   = 9.2;                              // 取付穴 9mm + 印刷の縮み分
jack_flange = 0;                                // つばを沈める座ぐり (0 = なし。現物を見てから)
jack_seat   = 0.6;                              // つばを沈める深さ
end_wall    = 2.0;                              // ｼﾞｬｯｸを付ける端の壁の厚み (ﾈｼﾞ長に合わせる)
jack_y = (usb_y0 - 0.2 - wall + BD) / 2;        // 奥行きの真ん中
jack_z = 7.0;                                   // 上面からの高さ (中心)
jacks  = [[0, "COM"], [1, "Ω"]];                // [0=左 / 1=右, 正面の刻印]
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
    // 中 (底から inner_h まで)。左右の端は end_wall
    translate([end_wall, y0 + wall, -eps]) cube([BW - 2*end_wall, y1 - y0 - 2*wall, inner_h + eps]);
    // USB-C の口 (ﾌﾟﾗｸﾞの太い所も入るように)
    translate([usb_x, y0 - eps, hdr_h + pcb_t + usb_h/2]) rotate([-90, 0, 0])
      linear_extrude(wall + 1) offset(r = 2) square([12.6 - 4, 7.0 - 4], center = true);
    // LED の窓 (天面)
    translate([led[0], led[1], inner_h - eps]) cylinder(d = 2.2, h = roof + 1);
    // ﾊﾞﾅﾅｼﾞｬｯｸの穴 (左右の端) と、つばの座ぐり
    if (use_jacks) for (j = jacks) {
      xo = j[0] == 0 ? -1 : BW - end_wall - 1;
      translate([xo, jack_y, jack_z]) rotate([0, 90, 0]) cylinder(d = jack_hole, h = end_wall + 2);
      if (jack_flange > 0) {
        xs = j[0] == 0 ? -1 : BW - jack_seat;
        translate([xs, jack_y, jack_z]) rotate([0, 90, 0]) cylinder(d = jack_flange + 0.6, h = jack_seat + 1);
      }
      // 正面の刻印 (端寄り)。正面は y = BD の面
      tx = j[0] == 0 ? 7.5 : BW - 7.5;
      translate([tx, y1 + eps, jack_z]) rotate([90, 0, 0]) linear_extrude(0.5)
        text(j[1], size = 3.2, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
    // 正面の細い溝 (Cap 風のﾗｲﾝ)。刻印の間だけ
    translate([14, y1 - 0.45, H * 0.45]) cube([BW - 28, 1, 0.6]);
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
  // 配線を天井側に留める小さなﾌｯｸ (基板の正面側の余白を通して左右へ)
  for (x = [12, 24, 60, 72]) translate([x - 1.5, BD - wall - 3.2, inner_h - 3.0]) difference() {
    cube([3, 3.2, 3.0 + eps]);
    translate([-1, 0.8, -eps]) cube([5, 1.6, 2.0]);
  }
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
  // ﾊﾞﾅﾅｼﾞｬｯｸ (つば φ11 + 本体 φ6 x 16mm + ﾅｯﾄ) の見本
  if (use_jacks) for (j = jacks) {
    s_ = j[0] == 0 ? 1 : -1;  xw = j[0] == 0 ? 0 : BW;
    translate([xw, jack_y, jack_z]) rotate([0, 90 * s_, 0]) {
      color(j[0] == 0 ? "black" : "red") translate([0, 0, -10]) cylinder(d = 10.5, h = 10);   // 外に出る部分 (仮)
      color(j[0] == 0 ? "black" : "red") cylinder(d = 8.8, h = end_wall);
      color("gold") translate([0, 0, end_wall]) cylinder(d = 8.8, h = 13.7);                 // 長さ 25.7 の残り (仮)
      color("silver") translate([0, 0, end_wall]) cylinder(d = 13.0, h = 2.5, $fn = 6);      // ﾅｯﾄ (仮 12mm 二面幅)
    }
  }
  if (use_jacks) color("tan") translate([BW - 24, jack_y, jack_z]) rotate([0, 90, 0]) cylinder(d = 2.4, h = 6.5);
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
