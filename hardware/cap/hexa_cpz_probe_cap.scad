// =====================================================================
//  HEXA STAGE  CPZ USB-C PWR + TEST ｷｬｯﾌﾟ v0.6  (Cap LoRa 風)
//  - 切り欠きなしの箱。左右対称 (中心 x42)。正面は IR の窓の手前 (背面から 16) でそろえ、
//    基板の所 (中央) だけ少し正面へ出す。IR (送受信) の窓は箱の外
//  - 取り付けは Cap LoRa-1262 と同じ: 背面に下がる「すそ」から M2 ねじ 2本で
//    本体背面のねじ穴 (x28 / x56、上面から 3.9 下) に留める
//  - 位置決め: LEGO 穴にﾋﾟﾝ2本 (基板も押さえる)
//  - 4mm ﾊﾞﾅﾅｼﾞｬｯｸ (秋月 MK-628) を左右の端に: 左 = COM (黒, GND) / 右 = Ω (赤, G22 →1kΩ→)
//
//  座標: x = 本体を正面から見た左→右 (左端 0)、y = 背面からの奥行き (背面 0)、z = 上面から上
//  寸法の出どころ: 公式 CardputerZero.stl を光線で測った値 (2026-11-27)
//  印刷は part="print" (天面を下、ｻﾎﾟｰﾄなし)
// =====================================================================
part = "print";      // "print" / "fittest" / "fit" (本体の STL に載せて確認、body.stl が要る)
$fn = 48;
eps = 0.01;

// ---- 本体 (公式 STL から)
ir   = [5.4, 14.4, 16.8, 20.2];  // IR の窓 (x0, x1, y0, y1) … 箱の正面はこれより手前
x_l  = 5.8;                   // 箱の左端 (背面側の平らな所)
x_r  = 78.2;                  // 箱の右端 (同じ。中心 42 で左右対称)
D    = 16.0;                  // 箱の奥行き (IR の窓 16.8 の 0.8 手前)
mid_w = 26.0;                 // 中央の出っ張りの幅 (基板 22 + 壁 + すき間 0.4)
BD   = 19.6;                  // 中央の出っ張りの正面 (基板 17.6 + 0.4 + 壁)
screws = [28.0, 56.0];        // 背面のねじ穴 (x)
screw_dz = 3.9;               // 上面からねじ穴の中心まで (下へ)
// ---- 基板 (v0.2)
bx  = 31.0;  PW = 22.0;  PD = 17.6;
hdr_h = 2.5;  pcb_t = 1.6;  usb_h = 3.26;
usb_x = bx + 11.0;  usb_y0 = -0.3;              // USB-C の口は背面から 0.3 出る
lego  = [[bx + 3, 4], [bx + 19, 4]];            // LEGO 穴 (x34/50, 背面から4)
led   = [bx + 7.2, 16.45];
led_window = false;                             // true = LED の上に φ2.2 の穴
// ---- 押さえ
press = 0.3;          // 柱が基板を押し下げる量 (0〜0.5)
// ---- ｷｬｯﾌﾟ
wall = 1.6;  roof = 1.6;  end_wall = 2.0;
H  = 15.2;                                      // Cap LoRa-1262 と同じ高さ
inner_h = H - roof;
y_in  = usb_y0 - 0.2;                           // 背面の壁の内側 (上面より上)
y_out = y_in - wall;                            // 背面の壁の外側 = すその外側 (-2.1)
skirt = 6.6;                                    // すそが上面から下がる量
r_side = 1.5;  r_top = 2.0;
// ---- ねじ (M2×4 ﾅﾍﾞ/ｷｬｯﾌﾟ。頭は 0.8 沈める → 本体に約 2.7 入る。M2×6 以上は使わない)
screw_hole = 2.3;  head_d = 4.2;  head_sink = 0.8;
// ---- 4mm ﾊﾞﾅﾅｼﾞｬｯｸ (秋月 MK-628: 取付穴 9mm / 径 10.5 / 長さ 25.7。裏側の長さは未確認)
use_jacks = true;                               // false = 穴なし (USB 給電だけで使う時)
jack_hole = 9.2;
jack_y = 7.0;                                   // 背面からの位置 (箱の奥行きの真ん中あたり)
jack_z = 8.2;                                   // 上面からの高さ (中心)

module rbox(x0, x1, y0, y1, z0, h) {
  // 縦の角を丸め、上の縁も丸めた箱 (下は平ら)
  r = r_side;
  translate([0, 0, z0]) hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r]) translate([x, y, 0]) {
    cylinder(r = r, h = h - r_top);
    translate([0, 0, h - r_top]) scale([1, 1, r_top / r]) sphere(r = r);
  }
}

mid = [42 - mid_w/2, 42 + mid_w/2];

module outer(sk = skirt) {
  rbox(x_l, x_r, y_out, D, 0, H);
  rbox(mid[0], mid[1], D - 4, BD, 0, H);
  // すそ: 背面に沿って下がる板 (本体背面に密着、y_out〜0)
  if (sk > 0) hull() for (x = [x_l + r_side, x_r - r_side]) {
    translate([x, y_out + r_side, -sk]) cylinder(r = r_side, h = sk + 1);
    translate([x, -eps, -sk]) cube([eps, eps, sk + 1]);
  }
}

module cavity() {
  translate([x_l + end_wall, y_in, -skirt - 1]) cube([x_r - x_l - 2*end_wall, D - wall - y_in, inner_h + skirt + 1]);
  translate([mid[0] + wall, y_in, -skirt - 1]) cube([mid_w - 2*wall, BD - wall - y_in, inner_h + skirt + 1]);
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

module usb_cut(extra = 0) {
  // USB-C の口 (extra = 背面より後ろへ伸ばす長さ、一体型でﾄﾚｲの壁も抜く時)
  translate([usb_x, y_out - eps - extra, hdr_h + pcb_t + usb_h/2]) rotate([-90, 0, 0])
    linear_extrude(wall + 1 + extra) offset(r = 2) square([12.6 - 4, 7.0 - 4], center = true);
}

module shell(sk = skirt, jk = use_jacks) {
  difference() {
    outer(sk);
    cavity();
    // 本体が入る所 (すその内側 = 本体背面より前、上面より下)
    translate([x_l - 1, 0, -skirt - 1]) cube([x_r - x_l + 2, BD + 1, skirt + 1]);
    usb_cut();
    // ねじ穴 (すそ)
    if (sk > 0) for (x = screws) translate([x, y_out - eps, -screw_dz]) rotate([-90, 0, 0]) {
      cylinder(d = screw_hole, h = -y_out + 1);
      cylinder(d = head_d, h = head_sink + eps);
    }
    if (led_window) translate([led[0], led[1], inner_h - eps]) cylinder(d = 2.2, h = roof + 1);
    if (jk) for (xo = [x_l - 1, x_r - end_wall - 1])
      translate([xo, jack_y, jack_z]) rotate([0, 90, 0]) cylinder(d = jack_hole, h = end_wall + 2);
  }
}

module inside() {
  for (p = lego) translate([p[0], p[1], 0]) {
    zb = hdr_h + pcb_t - press;
    translate([0, 0, zb]) cylinder(d = 6.0, h = inner_h - zb + eps);
    translate([0, 0, hdr_h + pcb_t]) peg();
  }
  // 配線ﾌｯｸ (正面側の天井)
  for (x = [28, 56]) translate([x - 1.5, D - wall - 3.2, inner_h - 3.0]) difference() {
    cube([3, 3.2, 3.0 + eps]);
    translate([-1, 0.8, -eps]) cube([5, 1.6, 2.0]);
  }
}

module cap(sk = skirt, jk = use_jacks) { shell(sk, jk); inside(); }

module fittest() {
  // ねじ 2本と LEGO ﾋﾟﾝ 2本の所だけ (位置と押さえの確認用)
  intersection() {
    cap();
    translate([screws[0] - 4, y_out - 1, -20]) cube([screws[1] - screws[0] + 8, 10 - y_out, 40]);
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
