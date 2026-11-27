// =====================================================================
//  HEXA STAGE  CPZ USB-C PWR + TEST ｷｬｯﾌﾟ v0.4  (公式 STL に合わせた版)
//  - 外形は本体上面の「平らな所」にぴったり: 背面側 (背面から 0〜16) は x 5.8〜78.2、
//    正面側 (16〜22) は x 2〜82 の2段。本体の外へはみ出さない (背面の USB-C の所だけ出る)
//  - 位置決め: 上面の左右の溝 (公式 Cap 用) に爪2本 + LEGO 穴にﾋﾟﾝ2本 (基板も押さえる)
//  - IR (送受信) の上は切り欠いて空ける
//  - 4mm ﾊﾞﾅﾅｼﾞｬｯｸ (秋月 MK-628) を左右の端に: 左 = COM (黒, GND) / 右 = Ω (赤, G22 →1kΩ→)
//
//  座標: x = 本体を正面から見た左→右 (左端 0)、y = 背面からの奥行き (背面 0)、z = 上面から上
//  寸法の出どころ: 公式 CardputerZero.stl の上面を光線で測った高さﾏｯﾌﾟ (2026-11-27)
//  印刷は part="print" (天面を下、ｻﾎﾟｰﾄなし)
// =====================================================================
part = "print";      // "print" / "fittest" / "fit" (本体の STL に載せて確認、body.stl が要る)
$fn = 48;
eps = 0.01;

// ---- 本体上面 (公式 STL から)
BD      = 21.2;               // 上面の奥行き (正面側の縁は x19〜65 で 21.15 から面取りがあるので、その手前まで)
step_y  = 16.0;               // ここから正面側が広くなる (背面ｹｰｽと正面ｹｰｽの境目 15.9)
back_x  = [5.8, 78.2];        // 背面側の平らな所
front_x = [2.0, 82.0];        // 正面側の平らな所
slots   = [[11.6, 16.4], [67.6, 72.4]];   // 上面の溝 (x)、背面から 0〜11.6、深さ 5.6
slot_y  = 11.6;  slot_d = 5.6;
ir      = [5.4, 14.4, 16.8, 20.2];        // IR の窓 2つ (x0, x1, y0, y1)
sd      = [18.0, 30.0, 16.8, 18.8];       // microSD の差し口 (塞ぐ。ｶｰﾄﾞは抜けない)
// ---- 基板 (v0.2)
bx  = 31.0;  PW = 22.0;  PD = 17.6;
hdr_h = 2.5;  pcb_t = 1.6;  usb_h = 3.26;
usb_x = bx + 11.0;  usb_y0 = -0.3;              // USB-C の口は背面から 0.3 出る
lego  = [[bx + 3, 4], [bx + 19, 4]];            // LEGO 穴 (x34/50, 背面から4)
led   = [bx + 7.2, 16.45];
// ---- 押さえ
press = 0.3;          // 柱が基板を押し下げる量 (0〜0.5)
// ---- ｷｬｯﾌﾟ
wall = 1.6;  roof = 1.6;  end_wall = 2.0;
H  = 15.2;                                      // Cap LoRa-1262 と同じ高さ
inner_h = H - roof;
y0 = usb_y0 - 0.2 - wall;                       // USB-C の出っ張りの背面 (ここだけ本体の外)
bump = [bx - 1.8, bx + PW + 1.8];
r_side = 1.5;  r_top = 2.0;
// ---- 爪 (上面の溝へ)
use_tabs = true;
tab_gap  = 0.35;      // 溝とのすき間 (片側)。溝の底は丸く、端は深さ約4mmしかない
tab_d    = 3.5;       // 溝に入る深さ (溝は真ん中 5.7、端 約4)
// ---- IR の切り欠き (正面側の縁から)
ir_open  = true;
ir_margin = 0.8;
// ---- 4mm ﾊﾞﾅﾅｼﾞｬｯｸ (秋月 MK-628: 取付穴 9mm / 径 10.5 / 長さ 25.7。ﾅｯﾄ等は未確認)
use_jacks = true;                               // false = 穴なし (USB 給電だけで使う時)
jack_hole = 9.2;
jack_y = 8.5;                                   // 背面からの位置 (背面側の段に付ける)
jack_z = 7.6;                                   // 上面からの高さ (中心)
jacks  = [[0, "COM"], [1, "Ω"]];
label_x = [21.5, 66.0];                         // 正面の刻印の位置 (IR の切り欠きを避ける)
keepout = [];                                   // 追加で抜きたい所 [[x0,x1,y0,y1], ...]

module rblock(x0, x1, ya, yb, h, r = r_side) {
  hull() for (x = [x0 + r, x1 - r], y = [ya + r, yb - r]) translate([x, y, 0]) {
    cylinder(r = r, h = h - r_top);
    translate([0, 0, h - r_top]) scale([1, 1, r_top / r]) sphere(r = r);
  }
}

module outer() {
  union() {
    rblock(back_x[0], back_x[1], 0, step_y + 1, H);
    rblock(front_x[0], front_x[1], step_y - 0.1, BD, H);
    rblock(bump[0], bump[1], y0, 6, H);
  }
}

module cavity() {
  translate([back_x[0] + end_wall, wall, -eps]) cube([back_x[1] - back_x[0] - 2*end_wall, step_y + 1 - wall, inner_h + eps]);
  translate([front_x[0] + end_wall, step_y - 0.5, -eps]) cube([front_x[1] - front_x[0] - 2*end_wall, BD - wall - step_y + 0.5, inner_h + eps]);
  translate([bump[0] + wall, y0 + wall, -eps]) cube([bump[1] - bump[0] - 2*wall, wall - y0 - wall + 0.1, inner_h + eps]);
}

module peg() {
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

module tab(s) {
  // 溝に入る爪。先は面取り。上面の高さで天井側の壁につなぐ薄い板付き
  w = s[1] - s[0] - 2*tab_gap;  l = slot_y - 2*tab_gap;
  translate([s[0] + tab_gap, tab_gap, 0]) {
    hull() {
      translate([0, 0, -tab_d + 0.6]) cube([w, l, tab_d - 0.6 + eps]);
      translate([0.4, 0.4, -tab_d]) cube([w - 0.8, l - 0.8, 0.6]);
    }
    cube([w, l, 1.0]);
  }
}

module shell() {
  difference() {
    outer();
    cavity();
    // USB-C の口
    translate([usb_x, y0 - eps, hdr_h + pcb_t + usb_h/2]) rotate([-90, 0, 0])
      linear_extrude(wall + 1) offset(r = 2) square([12.6 - 4, 7.0 - 4], center = true);
    // LED の窓
    translate([led[0], led[1], inner_h - eps]) cylinder(d = 2.2, h = roof + 1);
    // IR: 正面側の縁から、天井まで抜く
    if (ir_open) translate([ir[0] - ir_margin, ir[2] - ir_margin, -eps])
      cube([ir[1] - ir[0] + 2*ir_margin, BD - ir[2] + ir_margin + 1, H + 1]);
    // ﾊﾞﾅﾅｼﾞｬｯｸ
    if (use_jacks) for (j = jacks) {
      xo = j[0] == 0 ? back_x[0] - 1 : back_x[1] - end_wall - 1;
      translate([xo, jack_y, jack_z]) rotate([0, 90, 0]) cylinder(d = jack_hole, h = end_wall + 2);
      translate([label_x[j[0]], BD + eps, H * 0.5]) rotate([90, 0, 0]) linear_extrude(0.5)
        text(j[1], size = 3.2, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
    for (k = keepout) translate([k[0], k[2], -eps]) cube([k[1] - k[0], k[3] - k[2], H + 1]);
  }
}

module inside() {
  for (p = lego) translate([p[0], p[1], 0]) {
    zb = hdr_h + pcb_t - press;
    translate([0, 0, zb]) cylinder(d = 6.0, h = inner_h - zb + eps);
    translate([0, 0, hdr_h + pcb_t]) peg();
  }
  // 配線ﾌｯｸ (正面側の天井、IR の切り欠きを避ける)
  for (x = [21, 27, 57, 63]) translate([x - 1.5, BD - wall - 3.2, inner_h - 3.0]) difference() {
    cube([3, 3.2, 3.0 + eps]);
    translate([-1, 0.8, -eps]) cube([5, 1.6, 2.0]);
  }
}

module cap() {
  shell();
  inside();
  if (use_tabs) for (s = slots) tab(s);
}

module fittest() {
  intersection() {
    cap();
    translate([lego[0][0] - 5, y0 - 1, -20]) cube([lego[1][0] - lego[0][0] + 10, 11 - y0, 40]);
  }
}

module body() {
  // 公式 STL (body.stl: x 0〜84 / y 5〜59 = 高さ / z 0〜23.1 = 背面→正面) をこの座標へ
  multmatrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, -59], [0, 0, 0, 1]]) import("body.stl");
}

if (part == "print") translate([0, 0, H]) mirror([0, 0, 1]) cap();
else if (part == "fittest") translate([0, 0, H]) mirror([0, 0, 1]) fittest();
else if (part == "fit") { color([0.5, 0.52, 0.56]) body(); color("whitesmoke", 0.9) cap(); }
else if (part == "physfit") mirror([0, 1, 0]) { color([0.5, 0.52, 0.56]) body(); color("whitesmoke") cap(); }
else cap();
