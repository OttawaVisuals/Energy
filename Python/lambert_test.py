import math

A = 6378137.0
F_ELL = 1 / 298.257222101
E2 = F_ELL * (2 - F_ELL)
E = math.sqrt(E2)
PHI1 = math.radians(49)
PHI2 = math.radians(77)
PHI0 = math.radians(63.390675)
LAM0 = math.radians(-91.86666666666666)
X0 = 6200000.0
Y0 = 3000000.0


def m(phi):
    return math.cos(phi) / math.sqrt(1 - E2 * math.sin(phi) ** 2)


def t(phi):
    s = math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / (((1 - E * s) / (1 + E * s)) ** (E / 2))


M1, M2 = m(PHI1), m(PHI2)
T1, T2, T0 = t(PHI1), t(PHI2), t(PHI0)
N = (math.log(M1) - math.log(M2)) / (math.log(T1) - math.log(T2))
FF = M1 / (N * T1 ** N)
RHO0 = A * FF * T0 ** N


def forward(lon_deg, lat_deg):
    phi, lam = math.radians(lat_deg), math.radians(lon_deg)
    tt = t(phi)
    rho = A * FF * tt ** N
    theta = N * (lam - LAM0)
    x = X0 + rho * math.sin(theta)
    y = Y0 + RHO0 - rho * math.cos(theta)
    return x, y


def inverse(x, y):
    xp = x - X0
    yp = RHO0 - (y - Y0)
    rho = math.copysign(math.sqrt(xp * xp + yp * yp), N)
    theta = math.atan2(xp, yp)
    if N < 0:
        theta = math.atan2(-xp, -yp)
        rho = -rho
    tt = (rho / (A * FF)) ** (1 / N)
    lam = theta / N + LAM0
    phi = math.pi / 2 - 2 * math.atan(tt)
    for _ in range(10):
        s = math.sin(phi)
        phi_new = math.pi / 2 - 2 * math.atan(tt * (((1 - E * s) / (1 + E * s)) ** (E / 2)))
        if abs(phi_new - phi) < 1e-12:
            phi = phi_new
            break
        phi = phi_new
    return math.degrees(lam), math.degrees(phi)


for lon, lat in [(-75.6972, 45.4215), (-123.1207, 49.2827), (-52.7126, 47.5615), (-114.0719, 51.0447)]:
    x, y = forward(lon, lat)
    lon2, lat2 = inverse(x, y)
    print(f"{lon},{lat} -> {x:.1f},{y:.1f} -> {lon2:.6f},{lat2:.6f}  err={abs(lon-lon2):.2e},{abs(lat-lat2):.2e}")

print("A0A bbox sample point:", inverse(8924296.2, 2027053.0), inverse(9015750.7, 2203356.4))
