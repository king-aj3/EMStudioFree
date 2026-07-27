# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,line-too-long,too-many-lines,too-many-arguments,too-many-locals,too-many-statements
"""
Created on Tue 5 Sep 2022
Modified on Fri 21 Nov 2025 to update the version number (IS) to ITU-R P.2001-6

@authors: Ivica Stevanovic, Adrien Demarez
"""

import numpy as np

# EMStudio vendoring change (2026-07-10): the ITU digital maps are NOT
# bundled (ITU licensing: integral digital products, no redistribution) —
# load lazily on first map access, resolving P2001.npz through
# emstudio.coverage.itu_maps (user maps dir / env override / this directory).
_DIGITAL_MAPS = None


def _digital_maps():
    global _DIGITAL_MAPS
    if _DIGITAL_MAPS is None:
        from emstudio.coverage import itu_maps
        path = itu_maps.find_npz("P2001.npz")
        if path is None:
            raise FileNotFoundError(itu_maps.missing_message("P2001"))
        with np.load(path) as npz:
            _DIGITAL_MAPS = {k: npz[k].copy() for k in npz.files}
    return _DIGITAL_MAPS


class _LazyMaps:
    def __getitem__(self, k):
        return _digital_maps()[k]


DigitalMaps = _LazyMaps()


def bt_loss(d, h, z, GHz, Tpc, Phire, Phirn, Phite, Phitn, Hrg, Htg, Grx, Gtx, FlagVP):
    """
    P2001.bt_loss basic transmission loss according to ITU-R P.2001-6
    Lb = P2001.bt_loss(d, h, z, GHz, Tpc, Phire, Phirn, Phite, Phitn, Hrg, Htg, Grx, Gtx, FlagVP)

    This function computes path loss due to both signal enhancements and fading
    over the range from 0% to 100% of an average year according to the
    general purpose wide-range model as described in Recommendation ITU-R
    P.2001-4. The model covers the frequency range from 30 MHz to 50 GHz
    and it is most accurate for distances from 3 km to at least 1000 km.
    There is no specific lower limit, although the path length
    must be greater than zero. A prediction of basic transmission loss less
    than 20 dB should be considered unreliable. Similarly, there is no
    specific maximum distance. Antennas heights above ground level must be
    greater than zero. There is no specific maximum height above ground.
    The method is believed to be reliable for antenna altitudes
    up to 8000 m above sea level.

    Input parameters:
    Variable    Unit  Type    Ref         Description
    d           km    float   (2.1a)      Distance from transmitter of i-th profile point
    h           m     float   (2.1b)      Height of i-th profile point (amsl)
    z           z     int     (2.1c)      Zone code at distance di from transmitter (1 = Sea, 3 = Coastal Land, 4 = Inland)
    GHz         GHz   float   T.2.2.1     Frequency
    Tpc         %     float   T.2.2.1     Percentage of average year for which the predicted basic transmission loss is not exceeded
    Phire       deg   float   T.2.2.1     Receiver longitude, positive to east
    Phirn       deg   float   T.2.2.1     Receiver latitude, positive to north
    Phite       deg   float   T.2.2.1     Transmitter longitude, positive to east
    Phitn       deg   float   T.2.2.1     Transmitter latitude, positive to north
    Hrg         m     float   T.2.2.1     Receiving antenna height above ground
    Htg         m     float   T.2.2.1     Transmitting antenna height above ground
    Grx         dBi   float   T.2.2.1     Receiving antenna gain in the direction of the ray to the transmitting antenna
    Gtx         dBi   float   T.2.2.1     Transmitting antenna gain in the direction of the ray to the receiving antenna
    FlagVp            int     T.2.2.1     Polarisation: 1 = vertical; 0 = horizontal

    Output parameters:
    Lb     -   basic  transmission loss according to ITU-R P.2001-6

    Example:
    Lb = P2001.bt_loss(d, h, z, GHz, Tpc, Phire, Phirn, Phite, Phitn, Hrg, Htg, Grx, Gtx, FlagVP)

    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    07SEP22     Ivica Stevanovic, OFCOM         Initial version


    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
    OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.

    THE AUTHOR(S) AND OFCOM (CH) DO NOT PROVIDE ANY SUPPORT FOR THIS SOFTWARE

    This function calls other functions that are placed in the ./src folder
    Test functions to verify/validate the current implementation are placed  in ./test folder
    """

    # Constants

    c0 = 2.998e8
    Re = 6371

    ## 3.1 Limited percentage time

    Tpcp = Tpc + 0.00001 * (50 - Tpc) / 50  # Eq (3.1.1)
    Tpcq = 100 - Tpcp  # Eq (3.1.2)

    # Ensure that vector d is ascending
    if not np.all(np.diff(d) >= 0):
        raise ValueError("The array of path profile points d(i) must be in ascending order.")

    # Ensure that d[0] = 0 (Tx position)
    if d[0] > 0.0:
        raise ValueError("The first path profile point d[0] = " + str(d[0]) + " must be zero.")

    # 3.2 Path length, intermediate points, and fraction over sea

    dt = d[-1]
    # Eq (3.2.1)

    # make sure that there is enough points in the path profile
    if len(d) <= 10:
        raise ValueError("The number of points in path profile should be larger than 10")

    xx = np.logical_or(z == 1, np.logical_or(z == 3, z == 4))
    if np.any(xx == False):
        raise ValueError("The vector of zones z may contain only integers 1, 3, or 4.")

    if not (Tpc > 0 and Tpc < 100):
        raise ValueError("The percentage of the average year Tpc must be in the range (0, 100)")

    if Htg <= 0 or Hrg <= 0:
        raise ValueError("The antenna heights above ground Htg and Hrg must be positive.")

    if not FlagVP in (0, 1):
        raise ValueError("The polarization FlagVP can be either 0 (horizontal) or 1 (vertical).")

    # Calculate the longitude and latitude of the mid-point of the path, Phime,
    # and Phimn for dpnt = 0.5dt

    dpnt = 0.5 * dt
    Phime, Phimn, _, _ = great_circle_path(Phire, Phite, Phirn, Phitn, Re, dpnt)

    # Calculate the ground height in masl at the mid-point of the profile
    # according to whether the number of profile points n is odd or even
    # (3.2.2)

    n = len(d)

    if np.mod(n, 2) == 1:  # n is odd (3.2.2a)
        mp = int(0.5 * (n + 1) - 1)
        Hmid = h[mp]
    else:  # n is even (3.2.2b)
        mp = int(0.5 * n - 1)
        Hmid = 0.5 * (h[mp] + h[mp + 1])

    # Set the fraction of the path over sea, omega, (radio meteorological code 1)

    omega = path_fraction(d, z, 1)

    ## 3.3 Antenna altitudes and path inclinations

    # The Tx and Rx heights masl according to (3.3.1)

    Hts = Htg + h[0]
    Hrs = Hrg + h[-1]

    # Assign the higher and lower antenna heights above sea level (3.3.2)

    Hhi = max(Hts, Hrs)
    Hlo = min(Hts, Hrs)

    # Calculate the positive value of path inclination (3.3.3)

    Sp = (Hhi - Hlo) / dt

    ## 3.4 Climatic parameters
    # 3.4.1 Refractivity in the lowest 1 km

    DN_Median = DigitalMaps["DN_Median"]

    DN_SupSlope = DigitalMaps["DN_SupSlope"]

    DN_SubSlope = DigitalMaps["DN_SubSlope"]

    # Map Phime (-180, 180) to loncnt (0,360);

    Phime1 = Phime
    if Phime < 0:
        Phime1 = Phime + 360

    # Find SdN from file DN_Median.txt for the path mid-pint at Phime (lon),
    # Phimn (lat) - as a bilinear interpolation

    SdN = interp2(DN_Median, Phime1, Phimn, 1.5, 1.5)

    # Obtain Nd1km50 as in (3.4.1.1)

    Nd1km50 = -SdN

    # Find SdNsup from DN_SupSlope for the mid-point of the path

    SdNsup = interp2(DN_SupSlope, Phime1, Phimn, 1.5, 1.5)

    # Find SdNsub from DN_SubSlope for the mid-point of the path

    SdNsub = interp2(DN_SubSlope, Phime1, Phimn, 1.5, 1.5)

    # Obtain Nd1kmp as in (3.4.1.2)

    Nd1kmp = Nd1km50 + SdNsup * np.log10(0.02 * Tpcp) if Tpcp < 50 else Nd1km50 - SdNsub * np.log10(0.02 * Tpcq)

    # 3.4.2 Refractivity in the lowest 65 m
    # Obtain Nd65m1 from file dndz_01.txt for the midpoint of the path

    dndz_01 = DigitalMaps["dndz_01"]

    Nd65m1 = interp2(dndz_01, Phime1, Phimn, 1.5, 1.5)

    ## 3.5 Effective Earth-radius geometry
    # Median effective Earth radius (3.5.1)

    Reff50 = 157.0 * Re / (157.0 + Nd1km50)

    # Effective Earth curvature (3.5.2)

    Cp = (157.0 + Nd1kmp) / (157.0 * Re)

    # Effective Earth radius exceeded for p% time limited not to become
    # infinite (3.5.3)
    Reffp = 1.0 / Cp if Cp > 1e-6 else 1e6

    # The path length expressed as the angle subtended by d km at the center of
    # a sphere of effective Earth radius (3.5.4)

    Thetae = dt / Reff50
    # radians

    ## 3.6 Wavelength (3.6.1)

    Wave = 1e-9 * c0 / GHz

    ## 3.7 Path classification and terminal horizon parameters
    #  3.8 Effective heights and path roughness parameter

    Thetat, Thetar, Thetatpos, Thetarpos, Dlt, Dlr, Ilt, Ilr, _, _, _, _, Htea, Hrea, _, Hm, _, _, Htep, Hrep, FlagLos50 = smooth_earth_heights(d, h, Hts, Hrs, Reff50, Wave)

    ## 3.9 Troposhperic-scatter path segments

    Dtcv, Drcv, Phicve, Phicvn, Hcv, Phitcve, Phitcvn, Phircve, Phircvn = tropospheric_path(dt, Hts, Hrs, Thetae, Thetatpos, Thetarpos, Reff50, Phire, Phite, Phirn, Phitn, Re)

    ## 3.10 Gaseous absorbtion on surface paths
    # Use the method given in Attachment F, Sec. F.2 to calculate gaseous
    # attenuations due to oxygen, and for water vapour under both non-rain and
    # rain conditions for a surface path

    Aosur, Awsur, Awrsur, _, _, _, _ = gaseous_abs_surface(Phime, Phimn, Hmid, Hts, Hrs, dt, GHz)

    Agsur = Aosur + Awsur  # Eq (3.10.1)

    ## Sub-model 1

    # Calculate the diffraction loss not exceeded for p% time, as described in
    # Attachment A

    Ld_pol, _, _, _, _, _, _, _ = dl_p(d, h, Hts, Hrs, Htep, Hrep, GHz, omega, Reffp, Cp)

    Ld = Ld_pol[FlagVP]

    # Use the method given in Attachemnt B.2 to calculate the notional
    # clear-air zero-fade exceedance percentage time Q0ca

    Q0ca = multi_path_activity(GHz, dt, Hts, Hrs, Dlt, Dlr, h[Ilt], h[Ilr], Hlo, Thetat, Thetar, Sp, Nd65m1, Phimn, FlagLos50)

    # Perform the preliminary rain/wet-snow calculations in Attachment C.2
    # with the following inputs (4.1.1)

    phi_e = Phime
    phi_n = Phimn
    h_rainlo = Hlo
    h_rainhi = Hhi
    d_rain = dt

    a, b, c, dr, Q0ra, Fwvr, kmod, alpha_mod, Gm, Pm, flagrain = precipitation_fade_initial(GHz, Tpcq, phi_n, phi_e, h_rainlo, h_rainhi, d_rain, FlagVP)

    # Calculate A1 using (4.1.2)

    flagtropo = 0  # Normal propagation close to the surface of the Earth

    A1 = Aiter(Tpcq, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    # Calculate the sub-model 1 basic transmission loss not exceeded for p% time

    dfs = np.sqrt(dt**2.0 + ((Hts - Hrs) / 1000.0) ** 2.0)
    Lbfs = tl_free_space(GHz, dfs)  # Eq (3.11.1)

    Lbm1 = Lbfs + Ld + A1 + Fwvr * (Awrsur - Awsur) + Agsur  # Eq (4.1.4)

    ## Sub-model 2. Anomalous propagation

    # Use the method given in Attachment D to calculate basic transmission loss
    # not exceeded for p% time due to anomalous propagation Eq (4.2.1)

    Lba, _, _, _, _, _, _, _ = tl_anomalous_reflection(GHz, d, z, Hts, Hrs, Htea, Hrea, Hm, Thetat, Thetar, Dlt, Dlr, Phimn, omega, Reff50, Tpcp, Tpcq)

    Lbm2 = Lba + Agsur

    ## Sub-model 3. Troposcatter propagation

    # Use the method given in Attachment E to calculate the troposcatter basic
    # transmission loss Lbs as given by equation (E.17)

    Lbs, _, _ = tl_troposcatter(GHz, dt, Thetat, Thetar, Thetae, Phicvn, Phicve, Phitn, Phite, Phirn, Phire, Gtx, Grx, Reff50, Tpcp)

    # To avoid under-estimating troposcatter for short paths, limit Lbs (E.17)

    Lbs = max(Lbs, Lbfs)

    # Perform the preliminary rain/wet-snow calculations in Attachment C.2 from
    # the transmitter to common-volume path segment with the following inputs (4.3.1)

    phi_e = Phitcve
    phi_n = Phitcvn
    h_rainlo = Hts
    h_rainhi = Hcv
    d_rain = Dtcv

    a, b, c, dr, Q0ra, Fwvrtx, kmod, alpha_mod, Gm, Pm, flagrain = precipitation_fade_initial(GHz, Tpcq, phi_n, phi_e, h_rainlo, h_rainhi, d_rain, FlagVP)

    # Calculate A1 using (4.1.2)

    flagtropo = 1  # for troposcatter

    A2t = Aiter(Tpcq, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    # Perform the preliminary rain/wet-snow calculations in Attachment C.2 from
    # the receiver to common-volume path segment with the following inputs (4.3.1)

    phi_e = Phircve
    phi_n = Phircvn
    h_rainlo = Hrs
    h_rainhi = Hcv
    d_rain = Drcv

    a, b, c, dr, Q0ra, Fwvrrx, kmod, alpha_mod, Gm, Pm, flagrain = precipitation_fade_initial(GHz, Tpcq, phi_n, phi_e, h_rainlo, h_rainhi, d_rain, FlagVP)

    # Calculate A1 using (4.1.2)

    flagtropo = 1
    # for troposcatter

    A2r = Aiter(Tpcq, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    A2 = (A2t * (1 + 0.018 * Dtcv) + A2r * (1 + 0.018 * Drcv)) / (1 + 0.018 * dt)  # Eq (4.3.6)

    # Use the method given in Attachment F.3 to calculate gaseous attenuations
    # due to oxygen and for water vapour under both non-rain and rain
    # conditions for a troposcatter path (4.3.7)

    Aos, Aws, Awrs, _, _, _, _, _, _, _, _ = gaseous_abs_tropo(Phite, Phitn, Phire, Phirn, h[0], h[-1], Thetatpos, Thetarpos, Dtcv, Drcv, GHz)

    # Total gaseous attenuation under non-rain conditions is given by (4.3.7)

    Ags = Aos + Aws

    ## Sub-model 3 basic transmission loss (4.3.8)

    Lbm3 = Lbs + A2 + 0.5 * (Fwvrtx + Fwvrrx) * (Awrs - Aws) + Ags

    ## 4.4 Sub-model 4. Sporadic - E

    Lbm4, _, _, _, _, _, _, _, _, _, _, _, _, _, _ = tl_sporadic_e(GHz, dt, Thetat, Thetar, Phimn, Phime, Phitn, Phite, Phirn, Phire, Dlt, Dlr, Reff50, Re, Tpcp)

    ## 5 Combining sub-model results

    # 5.1 Combining sub-models 1 and 2

    Lm = min(Lbm1, Lbm2)

    Lbm12 = Lm - 10.0 * np.log10(10.0 ** (-0.1 * (Lbm1 - Lm)) + 10.0 ** (-0.1 * (Lbm2 - Lm)))

    # 5.2  Combining sub-models 1+2, 3, and 4

    Lm = min([Lbm12, Lbm3, Lbm4])

    Lb = Lm - 5.0 * np.log10(10.0 ** (-0.2 * (Lbm12 - Lm)) + 10.0 ** (-0.2 * (Lbm3 - Lm)) + 10.0 ** (-0.2 * (Lbm4 - Lm)))

    return Lb


def tl_sporadic_e(f, dt, thetat, thetar, phimn, phime, phitn, phite, phirn, phire, dlt, dlr, ae, Re, p):
    """tl_sporadic_e Sporadic-E transmission loss
    This function computes the basic transmission loss due to sporadic-E
    propagation as defined in ITU-R P.2001-4 (Attachment G)

      Input parameters:
      f       -   Frequency GHz
      dt      -   Total distance (km)
      thetat  -   Tx horizon elevation angle relative to the local horizontal (mrad)
      thetar  -   Rx horizon elevation angle relative to the local horizontal (mrad)
      phimn   -   Mid-point latitude (deg)
      phime   -   Mid-point longitude (deg)
      phitn   -   Tx latitude (deg)
      phite   -   Tx longitude (deg)
      phirn   -   Rx latitude (deg)
      phire   -   Rx longitude (deg)
      dlt     -   Tx to horizon distance (km)
      dlr     -   Rx to horizon distance (km)
      ae      -   Effective Earth radius (km)
      Re      -   Average Earth radius (km)
      p       -   Percentage of average year for which predicted basic loss
                  is not exceeded (%)

      Output parameters:
      Lbe    -   Basic transmission loss due to sporadic-E propagation (dB)
      Lbes1  -   Sporadic-E 1-hop basic transmission loss (dB)
      Lbes2  -   Sporadic-E 2-hop basic transmission loss (dB)
      Lp1t/r -   Diffraction losses at the two terminals for 1-hop propagation (dB)
      Lp2t/r -   Diffraction losses at the two terminals for 2-hop propagation (dB)
      Gamma1/2   Ionospheric loss for 1/2 hops (dB)
      FoEs1/2hop FoEs for 1/2 hop(s) sporadic-E propagation
      Phi1qe -   Longitude of the one-quarter point
      Phi1qn -   Latitude of the one-quarter point
      Phi3qe -   Longitude of the three-quarter point
      Phi3qn -   Latitude of the three-quarter point

      Example:
      Lbe, Lbes1, Lbes2, Lp1t, Lp2t, Lp1r, Lp2r, Gamma1, Gamma2, foes1, foes2, Phi1qe, Phi1qn, Phi3qe, Phi3qn = tl_sporadic_e(f, dt, thetat, thetar, phitn, phite, phirn, phire, dlt, dlr, ae, Re, p)


      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    18JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """

    # Attachment G: Sporadic-E propagation

    ## G.2 Derivation of FoEs

    if p < 1:
        p1 = 0.1
        foes1tab = DigitalMaps["FoEs0p1"]
        p2 = 1.0
        foes2tab = DigitalMaps["FoEs01"]
    elif p > 10:
        p1 = 10.0
        foes1tab = DigitalMaps["FoEs10"]
        p2 = 50.0
        foes2tab = DigitalMaps["FoEs50"]
    else:
        p1 = 1.0
        foes1tab = DigitalMaps["FoEs01"]
        p2 = 10.0
        foes2tab = DigitalMaps["FoEs10"]

    ## G.2 1-hop propagation

    # foes for the mid-point of the path

    # Map phime (-180, 180) to loncnt (0,360);

    if phime < 0:
        phime = phime + 360

    # Find foes1/2 from the correspoinding files for the path mid-point - as a bilinear interpolation

    foes1 = interp2(foes1tab, phime, phimn, 1.5, 1.5)
    foes2 = interp2(foes2tab, phime, phimn, 1.5, 1.5)

    FoEs1hop = foes1 + (foes2 - foes1) * (np.log10(p / p1)) / (np.log10(p2 / p1))  # Eq (G.1.1)

    # Ionospheric loss for one hop

    Gamma1 = (40.0 / (1 + dt / 130.0 + (dt / 250.0) ** 2) + 0.2 * (dt / 2600.0) ** 2) * (1000.0 * f / FoEs1hop) ** 2 + np.exp((dt - 1660) / 280.0)  # Eq (G.2.1)

    # Slope path length

    hes = 120.0

    l1 = 2 * (ae**2 + (ae + hes) ** 2 - 2 * ae * (ae + hes) * np.cos(dt / (2 * ae))) ** 0.5  # Eq (G.2.2)

    # free space loss for the slope distance:

    Lbfs1 = tl_free_space(f, l1)  # Eq (G.2.3)

    # ray take-off angle above the horizontal at both terminals for 1 hop

    alpha1 = dt / (2 * ae)

    epsr1 = 0.5 * np.pi - np.arctan(ae * np.sin(alpha1) / (hes + ae * (1 - np.cos(alpha1)))) - alpha1  # Eq (G.2.4)

    # Diffraction angles for the two terminals

    delta1t = 0.001 * thetat - epsr1
    delta1r = 0.001 * thetar - epsr1  # (G.2.5)

    # Diffraction parameters (G.2.6)

    nu1t = (1 if delta1t >= 0 else -1) * 3.651 * np.sqrt(1000 * f * dlt * (1 - np.cos(delta1t)) / np.cos(0.001 * thetat))
    nu1r = (1 if delta1r >= 0 else -1) * 3.651 * np.sqrt(1000 * f * dlr * (1 - np.cos(delta1r)) / np.cos(0.001 * thetar))

    # Diffraction lossess at the two terminals (G.2.7)

    Lp1t = dl_knife_edge(nu1t)

    Lp1r = dl_knife_edge(nu1r)

    # Sporadic-E 1-hop basic transmission loss (G.2.8)

    Lbes1 = Lbfs1 + Gamma1 + Lp1t + Lp1r

    ## G.3 2-hop propagation

    # Latitude and longitude of the one-quarter point

    Phi1qe, Phi1qn, _, _ = great_circle_path(phire, phite, phirn, phitn, Re, 0.25 * dt)
    Phi3qe, Phi3qn, _, _ = great_circle_path(phire, phite, phirn, phitn, Re, 0.75 * dt)

    # foes for one-quarter point
    # Map phime (-180, 180) to loncnt (0,360);

    phie = Phi1qe + 360 if Phi1qe < 0 else Phi1qe

    # Find foes1/2 from the correspoinding files for the one-quorter-point - as a bilinear interpolation

    foes1 = interp2(foes1tab, phie, Phi1qn, 1.5, 1.5)
    foes2 = interp2(foes2tab, phie, Phi1qn, 1.5, 1.5)

    FoEs2hop1q = foes1 + (foes2 - foes1) * (np.log10(p / p1)) / (np.log10(p2 / p1))  # Eq (G.1.1)

    # foes for three-quarter point
    # Map phie (-180, 180) to loncnt (0,360);

    phie = Phi3qe + 360 if Phi3qe < 0 else Phi3qe

    # Find foes1/2 from the correspoinding files for the one-quorter-point - as a bilinear interpolation

    foes1 = interp2(foes1tab, phie, Phi3qn, 1.5, 1.5)
    foes2 = interp2(foes2tab, phie, Phi3qn, 1.5, 1.5)

    FoEs2hop3q = foes1 + (foes2 - foes1) * (np.log10(p / p1)) / (np.log10(p2 / p1))  # Eq (G.1.1)

    # Obtain FoEs2hop as the lower of the two values calculated above

    FoEs2hop = min(FoEs2hop1q, FoEs2hop3q)

    # Ionospheric laps for two hops (G.3.1)

    Gamma2 = (40.0 / (1 + (dt / 260.0) + (dt / 500.0) ** 2) + 0.2 * (dt / 5200.0) ** 2) * (1000.0 * f / FoEs2hop) ** 2 + np.exp((dt - 3220.0) / 560.0)

    # Slope path length

    l2 = 4 * (ae**2 + (ae + hes) ** 2 - 2 * ae * (ae + hes) * np.cos(dt / (4.0 * ae))) ** 0.5
    # Eq (G.3.2)

    # Free-space loss for this slope

    Lbfs2 = tl_free_space(f, l2)  # Eq (G.3.3)

    # Ray take-off angle above the local horiozntal at both terminals for 2
    # hops (G.3.4)

    alpha2 = dt / (4.0 * ae)

    epsr2 = 0.5 * np.pi - np.arctan(ae * np.sin(alpha2) / (hes + ae * (1 - np.cos(alpha2)))) - alpha2

    # Diffraction angles for the two terminals (G.3.5)

    delta2t = 0.001 * thetat - epsr2
    delta2r = 0.001 * thetar - epsr2

    # Corresponding diffraction parameters (G.3.6)

    nu2t = (1 if delta2t >= 0 else -1) * 3.651 * np.sqrt(1000 * f * dlt * (1 - np.cos(delta2t)) / np.cos(0.001 * thetat))
    nu2r = (1 if delta2r >= 0 else -1) * 3.651 * np.sqrt(1000 * f * dlr * (1 - np.cos(delta2r)) / np.cos(0.001 * thetar))

    # Diffraction lossess at the two terminals (G.3.7)

    Lp2t = dl_knife_edge(nu2t)
    Lp2r = dl_knife_edge(nu2r)

    # Sporadic-E two-hop basic transmission loss

    Lbes2 = Lbfs2 + Gamma2 + Lp2t + Lp2r

    ## G.4 Basic transmission loss (G.4.1)

    if Lbes1 < Lbes2 - 20:
        Lbe = Lbes1
    elif Lbes2 < Lbes1 - 20:
        Lbe = Lbes2
    else:
        Lbe = -10 * np.log10(10 ** (-0.1 * Lbes1) + 10 ** (-0.1 * Lbes2))

    return Lbe, Lbes1, Lbes2, Lp1t, Lp2t, Lp1r, Lp2r, Gamma1, Gamma2, FoEs1hop, FoEs2hop, Phi1qe, Phi1qn, Phi3qe, Phi3qn


def gaseous_abs_tropo(phi_te, phi_tn, phi_re, phi_rn, h1, hn, thetatpos, thetarpos, dtcv, drcv, f):
    """gaseous_abs_tropo Gaseous absorbtion for a troposcatter path
    This function computes gaseous absorbtion for a complete troposcater
    path, from Tx to Rx via the common scattering volume
    and water-vapour as defined in ITU-R P.2001-4 Attachment F.3
    The formulas are valid for frequencies not greater than 54 GHz.

    Input parameters:
    phi_te    -   Tx Longitude (deg)
    phi_tn    -   Tx Latitude  (deg)
    phi_re    -   Rx Longitude (deg)
    phi_rn    -   Rx Latitude  (deg)
    h1        -   Ground height at the transmitter point of the profile (masl)
    hn        -   Ground height at the receiver point of the profile (masl)
    thetatpos -   Horizon elevation angle relative to the local horizontal
                  as viewed from Tx (limited to be positive) (mrad)
    thetarpos -   Horizon elevation angle relative to the local horizontal
                  as viewed from Rx (limited to be positive) (mrad)
    dtcv      -   Tx terminal to troposcatter common volume distance
    drcv      -   Rx terminal to troposcatter common volume distance
    f         -   Frequency (GHz), not greater than 54 GHz

    Output parameters:
    Aos       -   Attenuation due to oxygen for the complete troposcatter path (dB)
    Aws       -   Attenuation due to water-vapour under non-rain conditions for the complete path(dB)
    Awrs      -   Attenuation due to water-vapour under rain conditions for the complete path(dB)
    Aotcv     -   Attenuation due to oxygen for the Tx-cv path (dB)
    Awtcv     -   Attenuation due to water-vapour under non-rain conditions for the Tx-cv path(dB)
    Awrtcv    -   Attenuation due to water-vapour under rain conditions for the Tx-cv path(dB)%
    Aorcv     -   Attenuation due to oxygen for the Rx-cv path (dB)
    Awrcv     -   Attenuation due to water-vapour under non-rain conditions for the Rx-cv path(dB)
    Awrrcv    -   Attenuation due to water-vapour under rain conditions for the Rx-cv path(dB)%
    Wvsurtx   -   Surface water-vapour density under non-rain conditions at the Tx (g/m^3)
    Wvsurrx   -   Surface water-vapour density under non-rain conditions at the Rx (g/m^3)

    Example:
    Aos, Aws, Awrs, Aotcv, Awtcv, Awrtcv, Aorcv, Awrcv, Awrrcv, Wvsurtx, Wvsurrx = gaseous_abs_tropo(phi_te, phi_tn, phir_re, phi_rn, h1, hn, thetatpos, thetarpos,  dtcv, drcv,  f)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    18JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """

    # Obtain surface water-vapour density under non-rain conditions at the
    # location of Tx from the data file surfwv_50_fixed.txt

    surfwv_50_fixed = DigitalMaps["surfwv_50_fixed"]

    # Map phi_te (-180, 180) to loncnt (0,360);

    if phi_te < 0:
        phi_te = phi_te + 360

    # Find rho_sur from file surfwv_50_fixed.txt as a bilinear interpolation

    rho_sur = interp2(surfwv_50_fixed, phi_te, phi_tn, 1.5, 1.5)

    Wvsurtx = rho_sur

    # Use the method in Attachment F.4 to get the gaseous attenuations due to
    # oxygen and for water vapour under both non-rain and rain conditions for
    # the Tx-cv path (F.3.1)
    h_sur = h1
    theta_el = thetatpos
    dcv = dtcv

    Aotcv, Awtcv, Awrtcv = gaseous_abs_tropo_t2cv(rho_sur, h_sur, theta_el, dcv, f)

    # Obtain surface water-vapour density under non-rain conditions at the
    # location of Rx from the data file surfwv_50_fixed.txt

    # Map phi_re (-180, 180) to loncnt (0,360);

    if phi_re < 0:
        phi_re = phi_re + 360

    # Find rho_sur from file surfwv_50_fixed.txt as a bilinear interpolation

    rho_sur = interp2(surfwv_50_fixed, phi_re, phi_rn, 1.5, 1.5)

    Wvsurrx = rho_sur

    # Use the method in Attachment F.4 to get the gaseous attenuations due to
    # oxygen and for water vapour under both non-rain and rain conditions for
    # the Rx-cv path (F.3.2)
    h_sur = hn
    theta_el = thetarpos
    dcv = drcv

    Aorcv, Awrcv, Awrrcv = gaseous_abs_tropo_t2cv(rho_sur, h_sur, theta_el, dcv, f)

    # Gaseous attenuations for the complete troposcatter path (F.3.3)

    Aos = Aotcv + Aorcv

    Aws = Awtcv + Awrcv

    Awrs = Awrtcv + Awrrcv

    return Aos, Aws, Awrs, Aotcv, Awtcv, Awrtcv, Aorcv, Awrcv, Awrrcv, Wvsurtx, Wvsurrx


def gaseous_abs_tropo_t2cv(rho_sur, h_sur, theta_el, dcv, f):
    """gaseous_abs_tropo_t2cv Gaseous absorbtion for tropospheric terminal-common-volume path
    This function computes gaseous absorbtion for termina/common-volume
    troposcatter path as defined in ITU-R P.2001-4 Attachment F.4

    Input parameters:
    rho_sur   -   Surface water-vapour density under non rain conditions (g/m^3)
    h_sur     -   terrain height (masl)
    theta_el  -   elevation angle of path (mrad)
    dcv       -   Horizontal distance to the comon volume (km)
    f         -   Frequency (GHz), not greater than 54 GHz

    Output parameters:
    Ao       -   Attenuation due to oxygen (dB)
    Aw       -   Attenuation due to water-vapour under non-rain conditions (dB)
    Awr      -   Attenuation due to water-vapour under rain conditions (dB)


    Example:
    Ao, Aw, Awr= gaseous_abs_tropo_t2cv(rho_sur, h_sur, theta_el, dcv, f)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    18JUL16     Ivica Stevanovic, OFCOM         Initial version
      v1    13JUN17     Ivica Stevanovic, OFCOM         Octave compatibility (do -> d0)
      v2    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    # Use equation (F.6.2) to calculate the sea-level specific attenuation due
    # to water vapour under non-rain conditions gamma_w

    gamma_o, gamma_w = specific_sea_level_attenuation(f, rho_sur, h_sur)

    # Use equation (F.5.1) to calculate the surface water-vapour density under
    # rain conditions rho_surr

    rho_surr = water_vapour_density_rain(rho_sur, h_sur)

    # Use equation (F.6.2) to calculate the sea-level specifica ttenuation due
    # to water vapour undr rain conditions gamma_wr

    _, gamma_wr = specific_sea_level_attenuation(f, rho_surr, h_sur)

    # Calculate the quantities do and dw for oxygen and water vapour (F.4.1)

    d0 = 5.0 / (0.65 * np.sin(0.001 * theta_el) + 0.35 * np.sqrt((np.sin(0.001 * theta_el)) ** 2 + 0.00304))
    dw = 2.0 / (0.65 * np.sin(0.001 * theta_el) + 0.35 * np.sqrt((np.sin(0.001 * theta_el)) ** 2 + 0.00122))

    # Effective distances for oxygen and water vapour (F.4.2)

    deo = d0 * (1 - np.exp(-dcv / d0)) * np.exp(-h_sur / 5000.0)

    dew = dw * (1 - np.exp(-dcv / dw)) * np.exp(-h_sur / 2000.0)

    # Attenuations due to oxygen, and for water vapour for both non-rain and
    # rain conditions (F.4.3)

    Ao = gamma_o * deo

    Aw = gamma_w * dew

    Awr = gamma_wr * dew

    return Ao, Aw, Awr


def tl_troposcatter(f, dt, thetat, thetar, thetae, phicvn, phicve, phitn, phite, phirn, phire, Gt, Gr, ae, p):
    """tl_troposcatter Troposcatter basic transmission loss
    This function computes the troposcatter basic transmission loss
    as defined in ITU-R P.2001-4 (Attachment E)

      Input parameters:
      f       -   Frequency GHz
      dt      -   Total distance (km)
      thetat  -   Tx horizon elevation angle relative to the local horizontal (mrad)
      thetar  -   Rx horizon elevation angle relative to the local horizontal (mrad)
      thetae  -   Angle subtended by d km at centre of spherical Earth (rad)
      phicvn  -   Troposcatter common volume latitude (deg)
      phicve  -   Troposcatter common volume longitude (deg)
      phitn   -   Tx latitude (deg)
      phite   -   Tx longitude (deg)
      phirn   -   Rx latitude (deg)
      phire   -   Rx longitude (deg)
      Gt, Gr  -   Gain of transmitting and receiving antenna in the azimuthal direction
                  of the path towards the other antenna and at the elevation angle
                  above the local horizontal of the other antenna in the case of a LoS
                  path, otherwise of the antenna's radio horizon, for median effective
                  Earth radius.
      ae      -   Effective Earth radius (km)
      p       -   Percentage of average year for which predicted basic loss
                  is not exceeded (%)

      Output parameters:
      Lbs    -   Troposcatter basic transmission loss (dB)
      theta  -   Scatter angle (mrad)
      climzone-  Climate zone (0,1,2,3,4,5,6)

      Example:
      Lbs, theta, climzone = tl_troposcatter(f, dt, thetat, thetar, thetae, phicvn, phicve, phitn, phite, phirn, phire, Gt, Gr, ae, p)


      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    18JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    13JUN17     Ivica Stevanovic, OFCOM         replaced load function calls to increase computational speed
      v2    11AUG17     Ivica Stevanovic, OFCOM         introduced a correction in TropoClim vector indices to cover the case
                                                        when the point is equally spaced from the two closest grid points
      v3    06SEP22     Ivica Stevanovic, OFCOM         translated to python

    """

    # Attachment E: Troposcatter

    ## E.2 Climatic classification

    latcnt = np.arange(89.75, -90, -0.5)  # Table 2.4.1
    loncnt = np.arange(-179.75, 180, 0.5)  # Table 2.4.1

    # Obtain TropoClim for phicvn, phicve from the data file "TropoClim.txt"

    TropoClim = DigitalMaps["TropoClim"]

    # The value at the closest grid point to phicvn, phicve should be taken

    (knorth,) = np.where(abs(phicvn - latcnt) == min(abs(phicvn - latcnt)))
    (keast,) = np.where(abs(phicve - loncnt) == min(abs(phicve - loncnt)))

    climzone = TropoClim[knorth[0], keast[0]]

    # In case the troposcatter common volume lies over the sea the climates at
    # both the transmitter and receiver locations should be determined

    if climzone == 0:
        (knorth,) = np.where(abs(phirn - latcnt) == min(abs(phirn - latcnt)))
        (keast,) = np.where(abs(phire - loncnt) == min(abs(phire - loncnt)))

        climzoner = TropoClim[knorth[0], keast[0]]

        (knorth,) = np.where(abs(phitn - latcnt) == min(abs(phitn - latcnt)))
        (keast,) = np.where(abs(phite - loncnt) == min(abs(phite - loncnt)))

        climzonet = TropoClim[knorth[0], keast[0]]

        # if both terminals have a climate zone corresponding to a land point,
        # the climate zone of the path is given by the smaller value of the
        # transmitter and receiver climate zones

        if climzoner > 0 and climzonet > 0:
            climzone = min(climzoner, climzonet)

            # if only one terminal has a climate zone corresponding to a land
            # point, then that climate zone defines the climate zone of the path

        elif climzonet > 0:
            climzone = climzonet

        elif climzoner > 0:
            climzone = climzoner

    # From Table E.1 assign meteorological and atmospheric parameters M,
    # gamma and equation

    if climzone > 6 or climzone < 0:
        climzone = 0
    M_arr = [116, 129.6, 119.73, 109.3, 128.5, 119.73, 123.2]
    gamma_arr = [0.27, 0.33, 0.27, 0.32, 0.27, 0.27, 0.27]
    eq_arr = [7, 8, 6, 9, 10, 6, 6]
    M = M_arr[climzone]
    gamma = gamma_arr[climzone]
    eq = eq_arr[climzone]

    ## E.3 Calculation of tropocscatter basic transmission loss

    # The scatter angle (E.1)

    theta = 1000 * thetae + thetat + thetar  # mrad

    # The loss term dependent on the common vaolume height

    H = 0.25e-3 * theta * dt  # Eq (E.3)

    htrop = 0.125e-6 * theta**2 * ae  # Eq (E.4)

    LN = 20 * np.log10(5 + gamma * H) + 4.34 * gamma * htrop  # Eq (E.2)

    # Angular distance of the scatter path based on median effective Earth
    # radius

    ds = 0.001 * theta * ae  # Eq (E.5)

    # Calculate Y90 (dB) using one od equations (E.6)-(E.10) as selected from
    # table E.1

    if eq == 6:
        Y90 = -2.2 - (8.1 - 0.23 * min(f, 4)) * np.exp(-0.137 * htrop)  # Eq (E.6)

    elif eq == 7:
        Y90 = -9.5 - 3 * np.exp(-0.137 * htrop)  # Eq (E.7)

    elif eq == 8:
        if ds < 100:
            Y90 = -8.2

        elif ds >= 1000:
            Y90 = -3.4

        else:
            Y90 = 1.006e-8 * ds**3 - 2.569e-5 * ds**2 + 0.02242 * ds - 10.2  # Eq (E.8)

    elif eq == 9:
        if ds < 100:
            Y90 = -10.845

        elif ds >= 465:
            Y90 = -8.4

        else:
            Y90 = -4.5e-7 * ds**3 + 4.45e-4 * ds**2 - 0.122 * ds - 2.645  # Eq (E.9)

    elif eq == 10:
        if ds < 100:
            Y90 = -11.5

        elif ds >= 550:
            Y90 = -4

        else:
            Y90 = -8.519e-8 * ds**3 + 7.444e-5 * ds**2 - 4.18e-4 * ds - 12.1  # Eq (E.10)

    # Conversion factor given by (E.11)

    C = 1.26 * (-np.log10((100.0 - p) / 50.0)) ** 0.63 if p >= 50 else -1.26 * (-np.log10(p / 50.0)) ** 0.63

    # Parameter Yp not exceeded for p% time (E.12)

    Yp = C * Y90

    # Limit the value of theta such that theta >= 1e-6

    theta = max(theta, 1e-6)

    # Distance and frequency dependent losses (E.13) and (E.14)

    Ldist = max(10 * np.log10(dt) + 30 * np.log10(theta) + LN, 20 * np.log10(dt) + 0.573 * theta + 20)

    Lfreq = 25 * np.log10(f) - 2.5 * (np.log10(0.5 * f)) ** 2

    # Aperture-to-medium copuling loss (E.15)

    Lcoup = 0.07 * np.exp(0.055 * (Gt + Gr))

    # Troposcatter basic transmission loss not exceeded for p% time (E.16)

    Lbs = M + Lfreq + Ldist + Lcoup - Yp

    return Lbs, theta, climzone


def tl_anomalous_reflection(f, d, z, hts, hrs, htea, hrea, hm, thetat, thetar, dlt, dlr, phimn, omega, ae, p, q):
    """anomalous_reflection Basic transmission loss associated with anomalous propagation
    This function computes the basic transmission loss associated with
    anomalous propagation as defined in ITU-R P.2001-4 (Attachment D)

      Input parameters:
      f       -   Frequency GHz
      d       -   Vector of distances di of the i-th profile point (km)
      z       -   Radio climatic zones 1 = Sea, 3 = Coastal inland, 4 = Inland
                  Vectors d and z each contain n+1 profile points
      hts     -   Transmitter antenna height in meters above sea level (i=0)
      hrs     -   Receiver antenna height in meters above sea level (i=n)
      htea    -   Effective height of Tx antenna above smooth surface(m amsl)
      hrea    -   Effective height of Rx antenna above smooth surface (m amsl)
      hm      -   Path roughness parameter (m)
      thetat  -   Tx horizon elevation angle relative to the local horizontal (mrad)
      thetar  -   Rx horizon elevation angle relative to the local horizontal (mrad)
      dlt     -   Tx to horizon distance (km)
      dlr     -   Rx to horizon distance (km)
      phimn   -   Mid-point latitude (deg)
      omega   -   the fraction of the path over sea
      ae      -   Effective Earth radius (km)
      p       -   Percentage of average year for which predicted basic loss
                  is not exceeded (%)
      q       -   Percentage of average year for which predicted basic loss
                  is exceeded (%)

      Output parameters:
      Lba    -   Basic transmission loss associated with ducting (dB)
      Aat    -   Time-dependent loss (dB) c.f. Attachment D.7
      Aad    -   Angular distance dependent loss (dB) c.f. Attachment D.6
      Aac    -   Total coupling loss to the anomalous propagation mechanism (dB) c.f. Attachment D.5
      Dct    -   Coast distance from Tx (km)
      Dcr    -   Coast distance from Rx (km)
      Dtm    -   Longest continuous land (inland or coastal) section of the path (km)
      Dlm    -   Longest continuous inland section of the path (km)

      Example:
      Lba, Aat, Aad, Aac, Dct, Dcr, Dtm, Dlm = tl_anomalous_reflection(f, d, h, z, hts, hrs, htea, hrea, thetat, thetar, dlt, dlr, omega, ae, p, q)


      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    15JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    28OCT19     Ivica Stevanovic, OFCOM         Changes in angular distance dependent loss according to ITU-R P.2001-3
      v2    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """

    dt = d[-1] - d[0]

    # Attachment D: Anomalous/layer-reflection model

    ## D.1 Characterize the radio-climatic zones dominating the path

    # Longest continuous land (inland or coastal) section of the path
    zoner = 34  # (3 = coastal) + (4 = inland)
    dtm = longest_cont_dist(d, z, zoner)

    # Longest continuous inland section of the path
    zoner = 4
    dlm = longest_cont_dist(d, z, zoner)

    ## D.2 Point incidence of ducting

    # Calculate a parameter depending on the longest inland section of the path
    # (D.2.1)

    tau = 1 - np.exp(-0.000412 * dlm**2.41)

    # Calculate parameter mu_1 characterizing the degree to which the path is
    # over land (D.2.2)

    mu1 = min((10 ** (-dtm / (16 - 6.6 * tau)) + 10 ** (-(2.48 + 1.77 * tau))) ** 0.2, 1)

    # Calculate parameter mu4 given by (D.2.3)

    mu4 = 10 ** ((-0.935 + 0.0176 * abs(phimn)) * np.log10(mu1)) if abs(phimn) <= 70 else 10 ** (0.3 * np.log10(mu1))

    # The point incidence of anomalous propagation for the path centre (D.2.4)

    b0 = mu1 * mu4 * 10 ** (-0.015 * abs(phimn) + 1.67) if abs(phimn) <= 70 else 4.17 * mu1 * mu4

    ## D.3 Site-shielding losses with respect to the anomalous propagatoin mechanism

    # Corrections to Tx and Rx horizon elevation angles (D.3.1)

    gtr = 0.1 * dlt
    grr = 0.1 * dlr

    # Modified transmitter and receiver horizon elevation angles (D.3.2)

    thetast = thetat - gtr  # mrad
    thetasr = thetar - grr  # mrad

    # Tx and Rx site-shielding losses with respect to the duct (D.3.3)-(D.3.4)

    Ast = 20 * np.log10(1 + 0.361 * thetast * np.sqrt(f * dlt)) + 0.264 * thetast * f ** (1.0 / 3.0) if thetast > 0 else 0
    Asr = 20 * np.log10(1 + 0.361 * thetasr * np.sqrt(f * dlr)) + 0.264 * thetasr * f ** (1.0 / 3.0) if thetasr > 0 else 0

    ## D.4 Over-sea surface duct coupling corrections

    # Obtain the distance from each terminal to the sea in the direction of the
    # other terminal (D.4.1)

    dct, dcr = distance_to_sea(d, z)

    # The over-sea surface duct coupling corrections for Tx and Rx
    # (D.4.2)-(D.4.3)

    Act = -3 * np.exp(-0.25 * dct**2) * (1 + np.tanh(0.07 * (50 - hts))) if omega >= 0.75 and dct <= dlt and dct <= 5 else 0
    Acr = -3 * np.exp(-0.25 * dcr**2) * (1 + np.tanh(0.07 * (50 - hrs))) if omega >= 0.75 and dcr <= dlr and dcr <= 5 else 0

    ## D.5 Total coupling loss to the anomalous propagation mechanism

    # Empirical correction to account for the increasing attenuation with
    # wavelength in ducted propagation (D.5.2)

    Alf = (45.375 - 137.0 * f + 92.5 * f**2) * omega if f < 0.5 else 0

    # Total coupling losses between the antennas and the anomalous propagation
    # mechanism (D.5.1)

    Aac = 102.45 + 20 * np.log10(f * (dlt + dlr)) + Alf + Ast + Asr + Act + Acr

    ## D.6 Angular-distance dependent loss

    # Specific angular attenuation (D.6.1)

    gammad = 5e-5 * ae * f ** (1.0 / 3.0)

    # Adjusted Tx and Rx horizon elevation angles (D.6.2)

    theta_at = min(thetat, gtr)  # mrad

    theta_ar = min(thetar, grr)  # mrad

    # Adjucted total path angular distance (D.6.3)

    theta_a = 1000 * dt / ae + theta_at + theta_ar  # mrad

    # Angular-distance dependent loss (D.6.4a,b)

    Aad = gammad * theta_a if theta_a > 0 else 0

    ## D.7 Distance and time-dependent loss

    # Distance adjusted for terrain roughness factor (D.7.1)

    dar = min(dt - dlt - dlr, 40)

    # Terrain roughness factor (D.7.2)

    mu3 = np.exp(-4.6e-5 * (hm - 10) * (43 + 6 * dar)) if hm > 10 else 1

    # A term required for the path geometr ycorrection  (D.7.3)

    alpha = -0.6 - 3.5e-9 * dt**3.1 * tau

    if alpha < -3.4:
        alpha = -3.4

    # Path geometry factor (D.7.4)

    mu2 = min((500 * dt**2 / (ae * (np.sqrt(htea) + np.sqrt(hrea)) ** 2)) ** alpha, 1)

    # Time percentage associated with anomalous propagation adjusted for
    # general location and specific properties of the path (D.7.5)

    bduct = b0 * mu2 * mu3

    # An exponent required fo rthe time-dependent loss (D.7.6)

    Gamma = 1.076 * np.exp(-1e-6 * dt**1.13 * (9.51 - 4.8 * np.log10(bduct) + 0.198 * (np.log10(bduct)) ** 2)) / ((2.0058 - np.log10(bduct)) ** 1.012)

    # Time dependent loss (D.7.7)

    Aat = -12 + (1.2 + 0.0037 * dt) * np.log10(p / bduct) + 12 * (p / bduct) ** Gamma + 50.0 / q

    ## D.8 Basic transmission loss associated with ducting (D.8.1)

    Lba = Aac + Aad + Aat

    return Lba, Aat, Aad, Aac, dct, dcr, dtm, dlm


def distance_to_sea(d, zone):
    """distance_to_sea Distance to the sea in the direction of the other terminal
    This function computes the distance from eacht terminal to the sea in
    the direction of the other terminal

    Input arguments:
    d       -   vector of distances in the path profile
    zone    -   vector of zones in the path profile
                4 - Inland, 3 - Coastal, 1 - See

    Output arguments:
    dct      -  coast distance from transmitter
    dcr      -  coast distance from receiver

    Example:
    dct, dcr = distance_to_sea(d, zone)

    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    15JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
    v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    # Find the path profile points belonging to sea (zone = 1) starting from Tx

    (kk,) = np.where(zone == 1)

    if np.size(kk) == 0:  # complete path is inland or inland coast
        dct = d[-1]
        dcr = d[-1]

    else:
        nt = kk[0]
        nr = kk[-1]

        dct = 0 if nt == 0 else (d[nt] + d[nt - 1]) / 2.0 - d[0]  # nt == 0 if Tx is over sea
        dcr = 0 if nr == len(zone) - 1 else d[-1] - (d[nr] + d[nr + 1]) / 2.0  # nr == len(zone) - 1 if Rx is over sea

    return dct, dcr


def longest_cont_dist(d, zone, zone_r):
    """
    longest_cont_dist Longest continuous path belonging to the zone_r
    dm = longest_cont_dist(d, zone, zone_r)
    This function computes the longest continuous section of the
    great-circle path (km) for a given zone_r

    Input arguments:
    d       -   vector of distances in the path profile
    zone    -   vector of zones in the path profile
                4 - Inland, 3 - Coastal, 1 - See
    zone_r  -   reference zone for which the longest continuous section
                is computed,  zone_r = 34 for combined inland-coastal land

    Output arguments:
    dm      -   the longest continuous section of the great-circle path (km) for a given zone_r

    Example:
    dm = longest_cont_dist(d, zone, zone_r)

    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    22JAN16     Ivica Stevanovic, OFCOM         First implementation in matlab
    v1    12FEB16     Ivica Stevanovic, OFCOM         included zone_r==12
    v2    08JUL16     Ivica Stevanovic, OFCOM         modified mapping to  GlobCover data format
                                                      before: 2 - Inland, 1 - Coastal land, 3 - Sea
                                                      now:    4 - Inland, 3 - Coastal land, 1 - Sea
    v3    18JUL16     Ivica Stevanovic, OFCOM         modified condition d(stop(i)<d(end)) --> stop(i) < nmax
    v4    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    v5    11NOV22     Ivica Stevanovic, OFCOM         Corrected a bug in the second if clause (suggested by Martin-Pierre Lussier @mplussier)   

    """
    dm = 0

    if zone_r == 34:
        start, stop = find_intervals((zone == 3) + (zone == 4))
    else:
        start, stop = find_intervals((zone == zone_r))

    n = len(start)
    nmax = len(d)

    for i in range(0, n):
        delta = 0
        if stop[i] < nmax - 1:
            delta += (d[stop[i] + 1] - d[stop[i]]) / 2.0

        if start[i] > 0:
            delta += (d[start[i]] - d[start[i] - 1]) / 2.0

        dm = max(d[stop[i]] - d[start[i]] + delta, dm)

    return dm


def tl_free_space(f, d):
    """tl_free_space Free-space basic transmission loss
    This function computes free-space basic transmission loss in dB
    as defined in ITU-R P.2001-4 Section 3.11

    Input parameters:
    f       -   Frequency (GHz)
    d       -   3D Distance (km)

    Output parameters:
    Lbfs    -   Free-space basic transmission loss (dB)


    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    13JUL16     Ivica Stevanovic, OFCOM  Mer       Initial version MATLAB
    v1    11FEB22     Ivica Stevanovic, OFCOM         Aligned to P.2001-4
    v2    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    Lbfs = 92.4 + 20 * np.log10(f) + 20 * np.log10(d)

    return Lbfs


def Aiter(q, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain):
    """Aiter Inverse cumulative distribution function of a propagation model
    This function computes the inverse cumulative distribution function of a
    propagation model as defined in ITU-R P.2001-4 in Attachment I

      Input parameters:
      q        -   Percentage of average year for which predicted
                   transmission loss is exceeded
      Q0ca     -   Notional zero-fade annual percentage time
      Q0ra     -   Percentage of an average year in which rain occurs
      flagtropo-   0 = surface path, 1 = tropospheric path
      a, b, c  -   Parameters defining cumulative distribution of rain rate
      dr       -   Limited path length for precipitation calculations
      kmod     -   Modified regression coefficients
      alpha_mod-   Modified regression coefficients
      Gm       -   Vector of attenuation multipliers
      Pm       -   Vector of probabilities
      flagrain -   1 = "rain" path, 0 = "non-rain" path

      Output parameters:
      AiterQ   -   Attenuation level of a propoagation mechanisms exceeded
                   for q% time

      Example:
      AiterQ = Aiter(q, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    15JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    ## Attachment I. Iterative procedure to invert cumulative distribution function

    # Set initial values of the high and low searc hlimits for attenuation and
    # the attenuation step size

    Ainit = 10

    Ahigh = Ainit / 2.0  # Eq (I.2.1)

    Alow = -Ainit / 2.0  # Eq (I.2.2)

    Astep = Ainit  # Eq (I.2.3)

    # Initialize the percentage times attenuations Ahigh and Alow are exceeded
    # (I.2.4)

    qhigh = Qiter(Ahigh, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    qlow = Qiter(Alow, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    ## Stage 1

    count = 0

    if q < qhigh or q > qlow:
        while count < 11:
            count = count + 1

            if q < qhigh:
                Alow = Ahigh
                qlow = qhigh
                Astep = 2 * Astep
                Ahigh = Ahigh + Astep
                qhigh = Qiter(Ahigh, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)
                continue  # Loop back to the start of search range iteration and repeat from there

            if q > qlow:
                Ahigh = Alow
                qhigh = qlow
                Astep = 2 * Astep
                Alow = Alow - Astep
                qlow = Qiter(Alow, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)
                continue  # Loop back to the start of search range iteration and repeat from there

        # end of Initial search range iteration

    # end  of only if q < qhigh and q > qlow

    ## Stage 2: Binary search

    # Evaluate Atry (I.2.5)

    Atry = 0.5 * (Alow + Ahigh)

    # Start of binary search iteration
    # Set the binary search accuracy

    Aacc = 0.01

    Niter = np.ceil(3.32 * np.log10(Astep / Aacc))

    count = 0

    while count <= Niter:
        count = count + 1

        # Calculate the percentage time attenuation Atry is exceeded (I.2.6)

        qtry = Qiter(Atry, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

        if qtry < q:
            Ahigh = Atry
        else:
            Alow = Atry

        Atry = 0.5 * (Alow + Ahigh)

    # end of Loop back to the start of binary search iteration and repeat from there

    AiterQ = Atry

    return AiterQ


def Qiter(Afade, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain):
    """Qiter Cumulative distribution function of a propagation model
    This function computes the cumulative distribution function of a
    propagation model as defined in ITU-R P.2001-4 in Sections 4.1 and 4.3

      Input parameters:
      Afade    -   Clear air fade (A>0) or enhancement (A<0)
      Q0ca     -   Notional zero-fade annual percantage time
      Q0ra     -   Percentage of an average year in which rain occurs
      flagtropo-   0 = surface path, 1 = tropospheric path
      a, b, c  -   Parameters defining cumulative distribution of rain rate
      dr       -   Limited path length for precipitation calculations
      kmod     -   Modified regression coefficients
      alpha_mod-   Modified regression coefficients
      Gm       -   Vector of attenuation multipliers
      Pm       -   Vector of probabilities
      flagrain -   1 = "rain" path, 0 = "non-rain" path

      Output parameters:
      QiterA   -   Cumulative distribution function of fade A



      Example:
      QiterA = Qiter(Afade, Q0ca, Q0ra, flagtropo, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version in MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python

    """

    # Compute Qrain(Afade) as defined in Attachment C.3
    QrainA = precipitation_fade(Afade, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain)

    # Compute Qcaf(Afade) as defined in Attachments B.4/5

    QcafA = clear_air_fade_surface(Afade, Q0ca) if flagtropo == 0 else clear_air_fade_tropo(Afade)

    # Function QiterA is defined for combined clear-air/precipitation fading
    # (4.1.3), (4.3.5)

    QiterA = QrainA * (Q0ra / 100) + QcafA * (1 - Q0ra / 100)

    return QiterA


def clear_air_fade_surface(A, Q0ca):
    """Percentage time a given clear-air fade level is exceeded on a surface path
    This function computes the percentage of the non-rain time a given fade
    in dB below the median signal level is exceeded on a surface path
    as defined in ITU-R P.2001-4 in Attachment B.4

      Input parameters:
      A        -   Clear air fade (A>0) or enhancement (A<0)
      Q0ca     -   Notional zero-fade annual percantage time
      Output parameters:
      Qcaf     -   Percentage time a given clear-air fade level is exceeded
                   on a surface path



      Example:
      Qcaf = clear_air_fade_surface(A, Q0ca)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    ## B.4 Percentage time a given clear-air fade level is exceeded on a surface path

    if A >= 0:
        qt = 3.576 - 1.955 * np.log10(Q0ca)  # Eq (B.4.1b)

        qa = 2 + (1 + 0.3 * 10 ** (-0.05 * A)) * 10 ** (-0.016 * A) * (qt + 4.3 * (10 ** (-0.05 * A) + A / 800.0))  # Eq (B.4.1a)

        Qcaf = 100 * (1 - np.exp(-(10 ** (-0.05 * qa * A)) * np.log(2)))  # Eq (B.4.1)

    else:
        qs = -4.05 - 2.35 * np.log10(Q0ca)  # Eq (B.4.2b)

        qe = 8 + (1 + 0.3 * 10 ** (0.05 * A)) * 10 ** (0.035 * A) * (qs + 12 * (10 ** (0.05 * A) - A / 800.0))  # Eq (B.4.2a)

        Qcaf = 100 * (np.exp(-(10 ** (0.05 * qe * A)) * np.log(2)))  # Eq (B.4.2)

    return Qcaf


def clear_air_fade_tropo(A):
    """Percentage time a given clear-air fade level is exceeded on a troposcatter path
    This function computes the percentage of the non-rain time a given fade
    in dB below the median signal level is exceeded on a troposcatter path
    as defined in ITU-R P.2001-4 in Attachment B.5

      Input parameters:
      A        -   Clear air fade (A>0) or enhancement (A<0)

      Output parameters:
      Qcaftropo-   Percentage time a given clear-air fade level is exceeded
                   on a troposcatter path



      Example:
      Qcaftropo = clear_air_fade_tropo(A)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    ## B.5 Percentage time a given clear-air fade level is exceeded on a troposcatter path

    return 100 if A < 0 else 0  # Qcaftropo = Eq (B.5.1a) if A < 0 else Eq (B.5.1b)


def precipitation_fade(Afade, a, b, c, dr, kmod, alpha_mod, Gm, Pm, flagrain):
    """precipitation_fade Percentage time for which attenuation is exceeded
    This function computes the percentage time during whicht it is raining
    for which a given attenuation Afade is exceeded as defined in ITU-R
    P.2001-4 in Attachment C.3

      Input parameters:
      Afade    -   Attenuation (dB)
      a, b, c  -   Parameters defining cumulative distribution of rain rate
      dr       -   Limited path length for precipitation calculations
      kmod     -   Modified regression coefficients
      alpha_mod-   Modified regression coefficients
      Gm       -   Vector of attenuation multipliers
      Pm       -   Vector of probabilities
      flagrain -   1 = "rain" path, 0 = "non-rain" path

      Output parameters
      QrainA   -  percentage time during which it is raining for which a
                  given attenuation Afade is exceeded
      Example:
      QrainA = precipitation_fade(Afade, a, b, c, dr, Q0ra, Fwvr, kmod, alpha_mod, Gm, Pm, flagrain)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    ## C.3 Percentage time a given precipitation fade level is exceeded

    if Afade < 0:
        QrainA = 100  # Eq (C.3.1a)

    else:
        if flagrain == 0:  # non-rain
            QrainA = 0  # Eq (C.3.1b)

        else:  # rain
            drlim = max(dr, 0.001)  # Eq (C.3.1e)

            Rm = (Afade / (Gm * drlim * kmod)) ** (1.0 / alpha_mod)  # Eq (C.3.1d)

            QrainA = 100 * np.sum(Pm * np.exp(-a * Rm * (b * Rm + 1) / (c * Rm + 1)))  # Eq (C.3.1c)

    return QrainA


def path_averaged_multiplier(hlo, hhi, hT):
    """path_averaged_multiplier Models path-averaged multiplier
    This function computes the path-averaged multiplier
    according to ITU-R Recommendation P.2001-4 Attachment C.5

      Input parameters:
      hlo, hhi  -   heights of the loewr and higher antennas (m)
      hT        -   rain height

      Output parameters:
      G         -   weighted average of the multiplier Gamma (multi_layer.m)

      Example:
      G = path_averaged_multiplier( hlo, hhi, hT )

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated in python
    """
    ## C.5 Path-averaged multiplier

    # Calculate the slices in which the two antennas lie (C.5.1)

    slo = int(1 + np.floor((hT - hlo) / 100.0))

    shi = int(1 + np.floor((hT - hhi) / 100.0))

    if slo < 1:  # path wholy above the melting layer
        return 0

    if shi > 12:  # path is wholy at or below the lower edge of the melting layer
        return 1

    if slo == shi:  # both antennas in the same melting-layer slice (C.5.2)
        return multi_layer(0.5 * (hlo + hhi) - hT)

    # Initialize G for use as an accumulator (C.5.3)

    G = 0.0

    # Calculate the required range of slice indices (C.5.4)

    sfirst = max(shi, 1)

    slast = min(slo, 12)

    delh = 0.0
    Q = 0.0

    for s in range(sfirst, slast + 1):
        if shi < s and s < slo:
            # In this case the slice is fully traversed by a section of the
            # path (C.5.5)

            delh = 100.0 * (0.5 - s)

            Q = 100.0 / (hhi - hlo)

        elif s == slo:
            # In this case the slice contains the lower antenna at hlo (C.5.6)

            delh = 0.5 * (hlo - hT - 100.0 * (s - 1))
            Q = (hT - 100.0 * (s - 1) - hlo) / (hhi - hlo)

        elif s == shi:
            # In this case the slice contains the higher antenna at hhi (C.5.7)

            delh = 0.5 * (hhi - hT - 100.0 * s)

            Q = (hhi - (hT - 100.0 * s)) / (hhi - hlo)

        # For delh calculated under one of the preceeding three conditions,
        # calculate the corresponding multiplier (C.5.8)

        Gamma_slice = multi_layer(delh)

        # Accumulate the multiplier (C.5.9)

        G = G + Q * Gamma_slice

    if slo > 12:  # lower antenna is below the melting layer
        # The fraction of the path below the layer (C.5.10)
        Q = (hT - 1200.0 - hlo) / (hhi - hlo)

        # Since the multiplier is 1 below the layer, G should be increased
        # according to (C.5.11)

        G = G + Q

    return G


def multi_layer(delh):
    """multi_layer Models the changes in specific attenuation within the melting layer
    This function computes the changes in specific attenuation at different
    heights within the melting layer according to ITU-R Recommendation
    P.2001-4 Attachment C.4

      Input parameters:
      delh     -   difference between a given height h and rain height hT (m)

      Output parameters:
      Gamma    -   attenuation multiplier

      Example:
      Gamma = multi_layer( delh )

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version
      v1    06SEP22     Ivica Stevanovic, OFCOM         tranlated to python
    """
    ## C.4 Melting-layer model

    if delh > 0:
        Gamma = 0.0

    elif delh < -1200:
        Gamma = 1.0

    else:
        Gamma = 4.0 * (1.0 - np.exp(delh / 70.0)) ** 2.0

        Gamma = Gamma / (1.0 + (1.0 - np.exp(-((delh / 600.0) ** 2.0))) ** 2.0 * (Gamma - 1.0))

    return Gamma


def p838(f, theta, pol):
    """p838 Recommendation ITU-R P.838-3
    This function computes the rain regression coefficients k and alpha for
    a given frequency, path inclination and polarization according to ITU-R
    Recommendation P.838-3

      Input parameters:
      f        -   Frequency (GHz)
      theta    -   Path inclination (radians)
      pol      -   Polarization 0 = horizontal, 1 = vertical

      Output parameters:
      k, alpha -   Rain regression coefficients

      Example:
      [ k, alpha ] = p838( f, theta, pol )

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    14JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """

    tau = 0.0 if pol == 0 else np.pi / 2.0  # horizontal polarization / vertical polarization

    # Coefficients for kH

    aj_kh = np.array([-5.3398, -0.35351, -0.23789, -0.94158])
    bj_kh = np.array([-0.10008, 1.2697, 0.86036, 0.64552])
    cj_kh = np.array([1.13098, 0.454, 0.15354, 0.16817])
    m_kh = -0.18961
    c_kh = 0.71147

    # Coefficients for kV

    aj_kv = np.array([-3.80595, -3.44965, -0.39902, 0.50167])
    bj_kv = np.array([0.56934, -0.22911, 0.73042, 1.07319])
    cj_kv = np.array([0.81061, 0.51059, 0.11899, 0.27195])
    m_kv = -0.16398
    c_kv = 0.63297

    # Coefficients for aH

    aj_ah = np.array([-0.14318, 0.29591, 0.32177, -5.3761, 16.1721])
    bj_ah = np.array([1.82442, 0.77564, 0.63773, -0.9623, -3.2998])
    cj_ah = np.array([-0.55187, 0.19822, 0.13164, 1.47828, 3.4399])
    m_ah = 0.67849
    c_ah = -1.95537

    # Coefficients for aV

    aj_av = np.array([-0.07771, 0.56727, -0.20238, -48.2991, 48.5833])
    bj_av = np.array([2.3384, 0.95545, 1.1452, 0.791669, 0.791459])
    cj_av = np.array([-0.76284, 0.54039, 0.26809, 0.116226, 0.116479])
    m_av = -0.053739
    c_av = 0.83433

    logkh = np.dot(aj_kh, np.exp(-(((np.log10(f) - bj_kh) / cj_kh) ** 2))) + m_kh * np.log10(f) + c_kh
    kh = 10 ** (logkh)

    logkv = np.dot(aj_kv, np.exp(-(((np.log10(f) - bj_kv) / cj_kv) ** 2))) + m_kv * np.log10(f) + c_kv
    kv = 10 ** (logkv)

    ah = np.dot(aj_ah, np.exp(-(((np.log10(f) - bj_ah) / cj_ah) ** 2))) + m_ah * np.log10(f) + c_ah

    av = np.dot(aj_av, np.exp(-(((np.log10(f) - bj_av) / cj_av) ** 2))) + m_av * np.log10(f) + c_av

    k = (kh + kv + (kh - kv) * (np.cos(theta)) ** 2 * np.cos(2 * tau)) / 2.0

    alpha = (kh * ah + kv * av + (kh * ah - kv * av) * (np.cos(theta)) ** 2 * np.cos(2 * tau)) / (2 * k)

    return k, alpha


def precipitation_fade_initial(f, q, phi_n, phi_e, h_rainlo, h_rainhi, d_rain, pol_hv):
    """precipitation_fade_initial Preliminary calculation of precipitation fading
    This function computes the preliminary parameters necessary for precipitation
    fading as defined in ITU-R P.2001-4 in Attachment C.2

      Input parameters:
      f        -   Frequency (GHz)
      q        -   Percentage of average year for which predicted basic
                   loss is exceeded (100-p)
      phi_n    -   Latitude for obtaining rain climatic parameters (deg)
      phi_e    -   Longitude for obtaining rain climatic parameters (deg
      h_rainlo -   Lower height of the end of the path for a precipitation calculation (m)
      h_rainlo -   Higher height of the end of the path for a precipitation calculation (m)
      d_rain   -   Length of the path for rain calculation (km)
      pol_hv   -   0 = horizontal, 1 = vertical polarization


      Output parameters:
      a, b, c  -   Parameters defining cumulative distribution of rain rate
      dr       -   Limited path length for precipitation calculations
      Q0ra     -   Percentage of an average year in which rain occurs
      Fwvr     -   Factor used to estimate the effect of additional water vapour under rainy conditions
      kmod     -   Modified regression coefficients
      alpha_mod-   Modified regression coefficients
      G        -   Vector of attenuation multipliers
      P        -   Vector of probabilities
      flagrain -   1 = "rain" path, 0 = "non-rain" path

      Example:
      a, b, c, dr, Q0ra, Fwvr, kmod, alpha_mod, G, P, flagrain = precipitation_fade_initial(f, q, phi_n, phi_e, h_rainlo, h_rainhi, d_rain, pol_hv)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    15JUL16     Ivica Stevanovic, OFCOM         Initial version
      v1    13JUN17     Ivica Stevanovic, OFCOM         replaced load calls to increase computational speed
      v2    07MAR18     Ivica Stevanovic, OFCOM         declared empty arrays G and P for no-rain path
      v3    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    ## C.2 Precipitation fading: Preliminary calculations

    if phi_e < 0:
        phi_e = phi_e + 360

    # Obtain Pr6 for phi_n, phi_e from the data file "Esarain_Pr6_v5.txt"
    # as a bilinear interpolation

    Esarain_Pr6 = DigitalMaps["Esarain_Pr6_v5"]

    Pr6 = interp2(Esarain_Pr6, phi_e, phi_n, 1.125, 1.125)

    # Obtain Mt for phi_n, phi_e from the data file "Esarain_Mt_v5.txt"
    # as a bilinear interpolation

    Esarain_Mt = DigitalMaps["Esarain_Mt_v5"]

    Mt = interp2(Esarain_Mt, phi_e, phi_n, 1.125, 1.125)

    # Obtain beta_rain for phi_n, phi_e from the data file "Esarain_Beta_v5.txt"
    # as a bilinear interpolation

    Esarain_Beta = DigitalMaps["Esarain_Beta_v5"]

    beta_rain = interp2(Esarain_Beta, phi_e, phi_n, 1.125, 1.125)

    # Obtain h0 for phi_n, phi_e from the data file "h0.txt"
    # as a bilinear interpolation

    data_h0 = DigitalMaps["h0"]

    h0 = interp2(data_h0, phi_e, phi_n, 1.5, 1.5)

    # Calculate mean rain height hr (C.2.1)

    hR = 360.0 + 1000.0 * h0

    # calculate the highest rain height hRtop (C.2.2)

    hRtop = hR + 2400.0

    if Pr6 == 0 or h_rainlo >= hRtop:
        flagrain = 0  # no rain path
        Q0ra = 0
        Fwvr = 0
        a = 0
        b = 0
        c = 0
        dr = 0
        kmod = 0
        alpha_mod = 0
        G = [0.0]
        P = [0.0]

    else:  # the path is classified as rain
        flagrain = 1

        # Values from table C.2.1
        H = np.arange(-2400, 2401, 100)
        Pi = np.array([0.000555, 0.000802, 0.001139, 0.001594, 0.002196, 0.002978,
                       0.003976, 0.005227, 0.006764, 0.008617, 0.010808, 0.013346,
                       0.016225, 0.019419, 0.022881, 0.026542, 0.030312, 0.034081,
                       0.037724, 0.04111 , 0.044104, 0.046583, 0.048439, 0.049589,
                       0.049978, 0.049589, 0.048439, 0.046583, 0.044104, 0.04111 ,
                       0.037724, 0.034081, 0.030312, 0.026542, 0.022881, 0.019419,
                       0.016225, 0.013346, 0.010808, 0.008617, 0.006764, 0.005227,
                       0.003976, 0.002978, 0.002196, 0.001594, 0.001139, 0.000802,
                       0.000555])

        # Calculate two intermediate parameters (C.2.3)

        Mc = beta_rain * Mt
        Ms = (1.0 - beta_rain) * Mt

        # Calculate the percentage of an average year in which rain occurs (C.2.4)

        Q0ra = Pr6 * (1.0 - np.exp(-0.0079 * Ms / Pr6))

        # Calculate the parameters defining the cumulative distribution of rain
        # rate (C.2.5)

        a1 = 1.09
        b1 = (Mc + Ms) / (21797.0 * Q0ra)
        c1 = 26.02 * b1

        a = a1
        b = b1
        c = c1

        # Calculate the percentage time approximating to the transition between
        # the straight and curved sections of the rain-rate cumulative
        # distribution when plotted ... (C.2.6)

        Qtran = Q0ra * np.exp(a1 * (2.0 * b1 - c1) / c1**2.0)

        # Path inclination angle (C.2.7)

        eps_rain = 0.001 * (h_rainhi - h_rainlo + 0.0) / d_rain  # radians

        # Use the method given in Recommendation ITU-R P.838 to calculate rain
        # regression coefficients k and alpha for the frequency, polarization
        # and path inclination

        if f < 1:  # compute theregression coefficient for 1 GHz
            k1GHz, alpha1GHz = p838(1.0, eps_rain, pol_hv)
            k = f * k1GHz  # Eq (C.2.8a)
            alpha = alpha1GHz  # Eq (C.2.8b)
        else:
            k, alpha = p838(f, eps_rain, pol_hv)

        # Limit the path length for precipitation (C.2.9)

        dr = min(d_rain, 300.0)
        drmin = max(dr, 1.0)

        # Calculate modified regression coefficients (C.2.10)

        kmod = 1.763**alpha * k * (0.6546 * np.exp(-0.009516 * drmin) + 0.3499 * np.exp(-0.001182 * drmin))
        alpha_mod = (0.753 + 0.197 / drmin) * alpha + 0.1572 * np.exp(-0.02268 * drmin) - 0.1594 * np.exp(-0.0003617 * drmin)

        # Initialize and allocate the arrays for attenuation multiplier and
        # probability of a particular case (with a maximum dimension 49 as in
        # table C.2.1

        Gm = np.zeros(len(Pi))
        Pm = np.zeros(len(Pi))

        # Initialize Gm(1)=1, set m=1

        Gm[0] = 1.0

        m = 0

        for n in range(0, 49):
            # For each line of Table C.2.1 for n from 1 to 49 do the following

            # a) Calculate rain height given by  (C.2.11)
            hT = hR + H[n]

            # b) If h_rainlo >= hT repeat from a) for the next avalue of n,
            # otherwise continue from c

            if h_rainlo >= hT:
                continue  # repeat from a) for the next value of n

            if h_rainhi > hT - 1200:
                # c.i) use the method in Attachment C.5 to set Gm to the
                # path-averaged multiplier for this path geometry relative to
                # the melting layer

                Gm[m] = path_averaged_multiplier(h_rainlo, h_rainhi, hT)

                # c.ii) set Pm = Pi(n) from Table C.2.1
                Pm[m] = Pi[n]

                # c.iii) if n < 49 add 1 to array index m

                if n < 48:
                    m = m + 1

                # c.iv) repeat fom a) for the next value of n

                continue

            else:
                # d) Accumulate Pi(n) from table C.2.1 into Pm, set Gm = 1 and
                # repeat from a) for the next value of n

                Pm[m] = Pm[m] + Pi[n]
                Gm[m] = 1.0

        # Set the number of values in arrays Gm and Pm according to (C.2.12)

        Mlen = m + 1

        G = Gm[0:Mlen]
        P = Pm[0:Mlen]

        # Calculate a factor used to estimate the effect of additional water
        # vapour under rainy conditions (C.2.13), (C.2.14)

        Rwvr = 6.0 * (np.log10(Q0ra / q) / np.log10(Q0ra / Qtran)) - 3.0

        Fwvr = 0.5 * (1 + np.tanh(Rwvr)) * np.dot(G, P)

    return a, b, c, dr, Q0ra, Fwvr, kmod, alpha_mod, G, P, flagrain


def zero_fade_annual_time(dca, epsca, hca, f, K, phimn):
    """zero_fade_annual_time Calculate the notional zero-fade annual percentage time
    This function computes the the notional zero-fade annual percentage time
    as defined in ITU-R P.2001-4 in Attachment B.3

      Input parameters:
      dca      -   path distance (km)
      epsca    -   Positive value of path inclination (mrad)
      hca      -   Antenna height in meters above sea level
      f        -   Frequency (GHz)
      K        -   Factor representing the statistics of radio-refractivity
                   lapse rate for the midpoint of the path
      phimn    -   mid-point latitude
      Output parameters:
      Q0ca   -   Notional zero-fade annual percantage time


      Example:
      Q0ca = zero_fade_annual_time(dca, epsca, hca, f, K, phimn)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         Initial version
    """

    # Notional zero-fade worst-month percentage time (B.3.1)

    qw = K * dca**3.1 * (1 + epsca) ** (-1.29) * f**0.8 * 10 ** (-0.00089 * hca)

    # Calculate the logarithmic climatic conversion factor (B.3.2)

    Cg = min(10.5 - 5.6 * np.log10(1.1 + (1 if abs(phimn) <= 45 else -1) * (abs(cosd(2 * phimn))) ** 0.7) - 2.7 * np.log10(dca) + 1.7 * np.log10(1 + epsca), 10.8)

    # Notional zero-fade annual percentage time (B.3.3)

    Q0ca = qw * 10 ** (-0.1 * Cg)

    return Q0ca


def multi_path_activity(f, dt, hts, hrs, dlt, dlr, hlt, hlr, hlo, thetat, thetar, epsp, Nd65m1, phimn, FlagLos50):
    """multi_path_activity Multipath fading calculation
    This function computes the the notional zero-fade annual percentage time
    for the whole path as defined in ITU-R P.2001-4 in Attachment B.2

      Input parameters:
      f        -   Frequency (GHz)
      hts      -   Transmitter antenna height in meters above sea level (i=0)
      hrs      -   Receiver antenna height in meters above sea level (i=n)
      dlt      -   Tx antenna horizon distance (km)
      dlr      -   Rx antenna horizon distance (km)
      hlt      -   Profile height at transmitter horizon (m)
      hlr      -   Profile height at receiver horizon (m)
      hlo      -   Lower antenna height (m)
      thetat   -   Horizon elevation angles relative to the local horizontal as viewed from Tx
      thetar   -   Horizon elevation angles relative to the local horizontal as viewed from Rx
      phimn    -   mid-point latitude
      dca      -   path distance (km)
      epsp     -   Positive value of path inclination (mrad)
      Nd65m1   -   Refractivity gradient in the lowest 65 m of the atmosphere exceeded for 1% of an average year
      phimn    -   Path midpoint latitude
      FlagLos50-   1 = Line-of-sight 50% time, 0 = otherwise

      Output parameters:
      Q0ca   -   Notional zero-fade annual percantage time for the whole path



      Example:
      Q0ca = multi_path_activity(f, dt, hts, hrs, dlt, dlr, hlt, hlr, hlo, thetat, thetar, epsp, Nd65m1, phimn)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         Initial version
    """
    ## B.2 Characterize multi-path activity

    # Factor representing the statistics of radio-refractivity lapse time

    K = 10 ** (-(4.6 + 0.0027 * Nd65m1))

    if FlagLos50 == 1:
        # Calculate the notional zero fade annual percentage using (B.2.2)

        Q0ca = zero_fade_annual_time(dt, epsp, hlo, f, K, phimn)

    else:
        # Calculate the notoinal zero-fade annual percentage time at the
        # transmitter end Q0cat using (B.2.3)

        Q0cat = zero_fade_annual_time(dlt, abs(thetat), min(hts, hlt), f, K, phimn)

        # Calculate th enotional zero-fade annual percentage time at the
        # receiver end Q0car using (B.2.4)

        Q0car = zero_fade_annual_time(dlr, abs(thetar), min(hrs, hlr), f, K, phimn)

        Q0ca = max(Q0cat, Q0car)  # Eq (B.2.5)

    return Q0ca


def dl_bull_smooth(d, h, htep, hrep, ap, f):
    """dl_bull_smooth Bullington part of the diffraction loss according to P.2001-4
    This function computes the Bullington part of the diffraction loss
    as defined in ITU-R P.2001-4 in Attachment A.5 (for a notional smooth profile)

      Input parameters:
      d       -   Vector of distances di of the i-th profile point (km)
      h       -   Vector of heights hi of the i-th profile point (meters
                  above mean sea level)
                  Both vectors d and h contain n+1 profile points
      htep     -   Effective transmitter antenna height in meters above sea level (i=0)
      hrep     -   Effective receiver antenna height in meters above sea level (i=n)
      ap      -   Effective earth radius in kilometers
      f       -   frequency expressed in GHz

      Output parameters:
      Ldbs   -   Bullington diffraction loss for a given smooth path
      Ldbks  -   Knife-edge diffraction loss for Bullington point: smooth path
      FlagLosps - 1 = LoS p% time for smooth path, 0 = otherwise

      Example:
      Ldbs, Ldbks = dl_bull_smooth(d, h, htep, hrep, ap, f)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         First implementation
    """

    # Wavelength
    c = 2.998e8
    lam = 1e-9 * c / f

    # Complete path length

    dtot = d[-1] - d[0]

    # Find the intermediate profile point with the highest slope of the line
    # from the transmitter to the point

    di = d[1:-1]

    Stim = max(500 * (dtot - di) / ap - htep / di)  # Eq (A.5.1)

    # Calculate the slope of the line from transmitter to receiver assuming a
    # LoS path

    Str = (hrep - htep) / dtot  # Eq (A.5.2)

    if Stim < Str:  # Case 1, Path is LoS
        FlagLosps = 1
        # Find the intermediate profile point with the highest diffraction
        # parameter nu:
        nu = (500 * di * (dtot - di) / ap - (htep * (dtot - di) + hrep * di) / dtot) * np.sqrt(0.002 * dtot / (lam * di * (dtot - di)))
        numax = max(nu)  # Eq (A.5.3)

        Ldbks = dl_knife_edge(numax)  # Eq (A.5.4)
    else:
        FlagLosps = 0
        # Path is NLOS

        # Find the intermediate profile point with the highest slope of the
        # line from the receiver to the point

        Srim = max(500 * di / ap - hrep / (dtot - di))  # Eq (A.5.5)

        # Calculate the distance of the Bullington point from the transmitter:

        dbp = (hrep - htep + Srim * dtot) / (Stim + Srim)  # Eq (A.5.6)

        # Calculate the diffraction parameter, nub, for the Bullington point

        nub = (htep + Stim * dbp - (htep * (dtot - dbp) + hrep * dbp) / dtot) * np.sqrt(0.002 * dtot / (lam * dbp * (dtot - dbp)))  # Eq (A.5.7)

        # The knife-edge loss for the Bullington point is given by

        Ldbks = dl_knife_edge(nub)  # Eq (A.5.8)

    # For Ldbs calculated using either (A.5.4) or (A.5.8), Bullington diffraction loss
    # for the path is given by

    Ldbs = Ldbks + (1 - np.exp(-Ldbks / 6.0)) * (10 + 0.02 * dtot)  # Eq (A.5.9)
    return Ldbs, Ldbks, FlagLosps


def dl_knife_edge(nu):
    """dl_knife_edge Knife edge diffraction loss
    This function computes knife-edge diffraction loss in dB
    as defined in ITU-R P.2001-4 Section 3.12

      Input parameters:
      nu      -   dimensionless parameter

      Output parameters:
      J       -   Knife-edge diffraction loss (dB)

      Example J = dl_knife_edge(nu)
      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         Initial version
    """
    J = 0

    if nu > -0.78:
        J = 6.9 + 20 * np.log10(np.sqrt((nu - 0.1) ** 2 + 1) + nu - 0.1)

    return J


def dl_bull_actual(d, h, hts, hrs, Cp, f):
    """dl_bull_actual Bullington part of the diffraction loss according to P.2001-4
    This function computes the Bullington part of the diffraction loss
    as defined in ITU-R P.2001-4 in Attachment A.4 (for the smooth profile)

      Input parameters:
      d       -   Vector of distances di of the i-th profile point (km)
      h       -   Vector of heights hi of the i-th profile point (meters
                  above mean sea level)
                  Both vectors d and h contain n+1 profile points
      hts     -   Effective transmitter antenna height in meters above sea level (i=0)
      hrs     -   Effective receiver antenna height in meters above sea level (i=n)
      Cp      -   Effective Earth curvature
      f       -   Frequency (GHz)

      Output parameters:
      Ldba   -   Bullington diffraction loss for a given actual path
      Ldbka  -   Knife-edge diffraction loss for Bullington point: actual path
      FlagLospa - 1 = LoS p% time for actual path, 0 = otherwise

      Example:
      Ldba, Ldbka, FlagLospa = dl_bull_actual(d, h, hts, hrs, Cp, f)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         First implementation
    """

    # Wavelength
    c = 2.998e8
    lam = 1e-9 * c / f

    # Complete path length

    dtot = d[-1] - d[0]

    # Find the intermediate profile point with the highest slope of the line
    # from the transmitter to the point

    di = d[1:-1]
    hi = h[1:-1]

    Stim = max((hi + 500 * Cp * di * (dtot - di) - hts) / di)  # Eq (A.4.1)

    # Calculate the slope of the line from transmitter to receiver assuming a
    # LoS path

    Str = (hrs - hts) / dtot  # Eq (A.4.2)

    if Stim < Str:  # Case 1, Path is LoS
        FlagLospa = 1

        # Find the intermediate profile point with the highest diffraction
        # parameter nu:
        nu = (hi + 500 * Cp * di * (dtot - di) - (hts * (dtot - di) + hrs * di) / dtot) * np.sqrt(0.002 * dtot / (lam * di * (dtot - di)))
        numax = max(nu)  # Eq (A.4.3)

        Ldbka = dl_knife_edge(numax)  # Eq (A.4.4)
    else:
        FlagLospa = 0
        # Path is NLOS

        # Find the intermediate profile point with the highest slope of the
        # line from the receiver to the point

        Srim = max((hi + 500 * Cp * di * (dtot - di) - hrs) / (dtot - di))  # Eq (A.4.5)

        # Calculate the distance of the Bullington point from the transmitter:

        dbp = (hrs - hts + Srim * dtot) / (Stim + Srim)  # Eq (A.4.6)

        # Calculate the diffraction parameter, nub, for the Bullington point

        nub = (hts + Stim * dbp - (hts * (dtot - dbp) + hrs * dbp) / dtot) * np.sqrt(0.002 * dtot / (lam * dbp * (dtot - dbp)))  # Eq (A.4.7)

        # The knife-edge loss for the Bullington point is given by

        Ldbka = dl_knife_edge(nub)  # Eq (A.4.8)

    # For Luc calculated using either (A.4.4) or (A.4.8), Bullington diffraction loss
    # for the path is given by

    Ldba = Ldbka + (1 - np.exp(-Ldbka / 6.0)) * (10 + 0.02 * dtot)  # Eq (A.4.9)
    return Ldba, Ldbka, FlagLospa


def dl_se(d, hte, hre, ap, f, omega):
    """dl_se spherical-Earth diffraction loss exceeded for p% time according to ITU-R P.2001-4
    This function computes the Spherical-Earth diffraction loss not exceeded
    for p% time for antenna heights hte and hre (m)
    as defined in Attachment A.2 of ITU-R P.2001-4

      Input parameters:
      d       -   Great-circle path distance (km)
      hte     -   Effective height of interfering antenna (m)
      hre     -   Effective height of interfered-with antenna (m)
      ap      -   the effective Earth radius in kilometers
      f       -   Frequency (GHz)
      omega   -   the fraction of the path over sea

      Output parameters:
      Ldsph   -   The spherical-Earth diffraction loss not exceeded for p% time
                  Ldsph(1) is for the horizontal polarization
                  Ldsph(2) is for the vertical polarization

      Example:
      Ldsph = dl_se(d, hte, hre, ap, lam, omega)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         Initial version

    """
    # Wavelength
    c0 = 2.998e8
    lam = 1e-9 * c0 / f

    # Calculate the marginal LoS distance for a smooth path

    dlos = np.sqrt(2 * ap) * (np.sqrt(0.001 * hte) + np.sqrt(0.001 * hre))  # Eq (A.2.1)

    if d >= dlos:
        # calculate diffraction loss Ldft using the method in Sec. A.3 for
        # adft = ap and set Ldsph to Ldft

        Ldsph = dl_se_ft(d, hte, hre, ap, f, omega)
        return Ldsph
    else:
        # calculate the smallest clearance between the curved-Earth path and
        # the ray between the antennas, hse

        c = (hte - hre) / (hte + hre)  # Eq (A.2.2d)
        m = 250 * d * d / (ap * (hte + hre))  # Eq (A.2.2e)

        b = 2 * np.sqrt((m + 1) / (3 * m)) * np.cos(np.pi / 3.0 + 1.0 / 3.0 * np.arccos(3.0 * c / 2.0 * np.sqrt(3.0 * m / (m + 1.0) ** 3)))  # Eq (A.2.2c)

        dse1 = d / 2.0 * (1.0 + b)  # Eq (A.2.2a)
        dse2 = d - dse1  # Eq (A.2.2b)

        hse = (hte - 500 * dse1 * dse1 / ap) * dse2 + (hre - 500 * dse2 * dse2 / ap) * dse1
        hse = hse / d  # Eq (A.2.2)

        # Calculate the required clearance for zero diffraction loss

        hreq = 17.456 * np.sqrt(dse1 * dse2 * lam / d)  # Eq (A.2.3)
        Ldsph = np.zeros(2)
        if hse > hreq:
            return Ldsph
        else:
            # calculate the modified effective Earth radius aem, which gives
            # marginal LoS at distance d

            aem = 500 * (d / (np.sqrt(hte) + np.sqrt(hre))) ** 2  # Eq (A.2.4)

            # Use the method in Sec. A3 for adft = aem to obtain Ldft

            Ldft = dl_se_ft(d, hte, hre, aem, f, omega)

            Ldsph[0] = 0 if Ldft[0] < 0 else (1 - hse / hreq) * Ldft[0]  # Eq (A.2.5)
            Ldsph[1] = 0 if Ldft[1] < 0 else (1 - hse / hreq) * Ldft[1]  # Eq (A.2.5)

    return Ldsph


def dl_se_ft(d, hte, hre, adft, f, omega):
    """dl_se_ft First-term part of spherical-Earth diffraction according to ITU-R P.2001-4
    This function computes the first-term part of Spherical-Earth diffraction
    as defined in Sec. A.3 of the ITU-R P.2001-4

      Input parameters:
      d       -   Great-circle path distance (km)
      hte     -   Effective height of interfering antenna (m)
      hre     -   Effective height of interfered-with antenna (m)
      adft    -   effective Earth radius (km)
      f       -   Frequency (GHz)
      omega   -   fraction of the path over sea

      Output parameters:
      Ldft   -   The first-term spherical-Earth diffraction loss not exceeded for p% time
                 Ldft(1) is for the horizontal polarization
                 Ldft(2) is for the vertical polarization

      Example:
      Ldft = dl_se_ft(d, hte, hre, adft, f, omega)

      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    13JUL16     Ivica Stevanovic, OFCOM         First implementation MATLAB
      v1    04AUG18     Ivica Stevanovic, OFCOM         epsr and sigma were
                                                        swapped in dl_se_ft_inner function call
      v2    06SEP22     Ivica Stevanovic, OFCOM         translated to python


    """

    # First-term part of the spherical-Earth diffraction loss over land

    Ldft_land = dl_se_ft_inner(22, 0.003, d, hte, hre, adft, f)

    # First-term part of the spherical-Earth diffraction loss over sea

    Ldft_sea = dl_se_ft_inner(80, 5, d, hte, hre, adft, f)

    # First-term spherical diffraction loss

    Ldft = omega * Ldft_sea + (1 - omega) * Ldft_land  # Eq (A.3.1)

    return Ldft


def dl_se_ft_inner(epsr, sigma, d, hte, hre, adft, f):
    """dl_se_ft_inner The inner routine of the first-term spherical diffraction loss
    This function computes the first-term part of Spherical-Earth diffraction
    loss exceeded for p% time for antenna heights
    as defined in Sec. A.3 of the ITU-R P.2001-4, equations (A3.2-A3.8)

        Input parameters:
        epsr    -   Relative permittivity
        sigma   -   Conductivity (S/m)
        d       -   Great-circle path distance (km)
        hte     -   Effective height of interfering antenna (m)
        hre     -   Effective height of interfered-with antenna (m)
        adft    -   effective Earth radius (km)
        f       -   frequency (GHz)

        Output parameters:
        Ldft   -   The first-term spherical-Earth diffraction loss not exceeded for p% time
                    implementing equations (30-37), Ldft(1) is for horizontal
                    and Ldft(2) for the vertical polarization

        Example:
        Ldft = dl_se_ft_inner(epsr, sigma, d, hte, hre, adft, f)

        Rev   Date        Author                          Description
        -------------------------------------------------------------------------------
        v0    13JUL16     Ivica Stevanovic, OFCOM         Initial implementation MATLAB
        v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """

    # Normalized factor for surface admittance for horizontal (1) and vertical
    # (2) polarizations

    K = np.zeros(2)
    K[0] = 0.036 * (adft * f) ** (-1.0 / 3.0) * ((epsr - 1) ** 2 + (18 * sigma / f) ** 2) ** (-1.0 / 4.0)  # Eq (A.3.2a)

    K[1] = K[0] * (epsr**2 + (18.0 * sigma / f) ** 2) ** (1.0 / 2.0)  # Eq (A.3.2b)

    # Earth ground/polarization parameter

    beta_dft = (1 + 1.6 * K**2 + 0.67 * K**4) / (1 + 4.5 * K**2 + 1.53 * K**4)  # Eq (A.3.3)

    # Normalized distance

    X = 21.88 * beta_dft * (f / adft**2) ** (1.0 / 3.0) * d  # Eq (A.3.4)

    # Normalized transmitter and receiver heights

    Yt = 0.9575 * beta_dft * (f**2.0 / adft) ** (1.0 / 3.0) * hte  # Eq (A.3.5a)

    Yr = 0.9575 * beta_dft * (f**2.0 / adft) ** (1.0 / 3.0) * hre  # Eq (A.3.5b)

    Fx = np.zeros(2)
    GYt = np.zeros(2)
    GYr = np.zeros(2)

    # Calculate the distance term given by:

    for ii in range(0, 2):
        if X[ii] >= 1.6:
            Fx[ii] = 11 + 10 * np.log10(X[ii]) - 17.6 * X[ii]
        else:
            Fx[ii] = -20 * np.log10(X[ii]) - 5.6488 * (X[ii]) ** 1.425  # Eq (A.3.6)

    Bt = beta_dft * Yt  # Eq (A.3.7a)

    Br = beta_dft * Yr  # Eq (A.3.7a)

    for ii in range(0, 2):
        if Bt[ii] > 2:
            GYt[ii] = 17.6 * (Bt[ii] - 1.1) ** 0.5 - 5 * np.log10(Bt[ii] - 1.1) - 8
        else:
            GYt[ii] = 20 * np.log10(Bt[ii] + 0.1 * Bt[ii] ** 3)

        if Br[ii] > 2:
            GYr[ii] = 17.6 * (Br[ii] - 1.1) ** 0.5 - 5 * np.log10(Br[ii] - 1.1) - 8
        else:
            GYr[ii] = 20 * np.log10(Br[ii] + 0.1 * Br[ii] ** 3)

        if GYr[ii] < 2 + 20 * np.log10(K[ii]):
            GYr[ii] = 2 + 20 * np.log10(K[ii])

        if GYt[ii] < 2 + 20 * np.log10(K[ii]):
            GYt[ii] = 2 + 20 * np.log10(K[ii])

    Ldft = -Fx - GYt - GYr  # Eq (A.3.8)

    return Ldft


def dl_p(d, h, hts, hrs, hte, hre, f, omega, ap, Cp):
    """dl_p Diffraction loss model not exceeded for p% of time according to P.2001-4
    [Ld, Ldsph, Ldba, Ldbs, Ldbka, Ldbks] = dl_p( d, h, hts, hrs, hte, hre, f, omega, ap, Cp )

    This function computes the diffraction loss not exceeded for p% of time
    as defined in ITU-R P.2001-4 (Attachment A)

      Input parameters:
      d       -   vector of distances di of the i-th profile point (km)
      h       -   vector hi of heights of the i-th profile point (meters
                  above mean sea level).
                  Both vectors h and d contain n+1 profile points
      hts     -   transmitter antenna height in meters above sea level (i=0)
      hrs     -   receiver antenna height in meters above sea level (i=n)
      hte     -   Effective height of interfering antenna (m amsl)
      hre     -   Effective height of interfered-with antenna (m amsl)
      f       -   frequency expressed in GHz
      omega   -   the fraction of the path over sea
      ap      -   Effective Earth radius (km)
      Cp      -   Effective Earth curvature

      Output parameters:
      Ldp    -   diffraction loss for the general path not exceeded for p%  of the time
                 according to Attachment A of ITU-R P.2001-4.
                 Ldp(1) is for the horizontal polarization
                 Ldp(2) is for the vertical polarization
      Ldshp  -   Spherical-Earth diffraction loss diffraction (A.2) for the actual path d and modified antenna heights
      Lba    -   Bullington diffraction loss for the actual path profile as calculated in A.4
      Lbs    -   Bullingtong diffraction loss for a smooth path profile as calculated in A.5
      Ldbka  -   Knife-edge diffraction loss for Bullington point: actual path
      Ldbks  -   Knife-edge diffraction loss for Bullington point: smooth path
      FlagLospa - 1 = LoS p% time for actual path, 0 = otherwise
      FlagLosps - 1 = LoS p% time for smooth path, 0 = otherwise

      Example:
      [Ld, Ldsph, Ldba, Ldbs, Ldbka, Ldbks, FlagLospa, FlagLosps] = dl_p( d, h, hts, hrs, hte, hre, f, omega, ap, Cp )


      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    06SEP22     Ivica Stevanovic, OFCOM         Initial version

    """

    dtot = d[-1]

    Ldsph = dl_se(dtot, hte, hre, ap, f, omega)

    Ldba, Ldbka, FlagLospa = dl_bull_actual(d, h, hts, hrs, Cp, f)

    Ldbs, Ldbks, FlagLosps = dl_bull_smooth(d, h, hte, hre, ap, f)
    Ld = np.zeros(2)
    Ld[0] = Ldba + max(Ldsph[0] - Ldbs, 0)  # Eq (A.1.1)
    Ld[1] = Ldba + max(Ldsph[1] - Ldbs, 0)  # Eq (A.1.1)

    return Ld, Ldsph, Ldba, Ldbs, Ldbka, Ldbks, FlagLospa, FlagLosps


def gaseous_abs_surface(phi_me, phi_mn, h_mid, hts, hrs, dt, f):
    """specific_sea_level_attenuation Specific sea-level attenuations (Attachment F.6)
     This function computes specific sea-level attenuations due to oxigen
     and water-vapour as defined in ITU-R P.2001-4 Attachment F.6
     The formulas are valid for frequencies not greater than 54 GHz.

     Input parameters:
     phi_me    -   Longitude of the mid-point of the path (deg)
     phi_mn    -   Latitude of the mid-point of the path (deg)
     h_mid     -   Ground height at the mid-point of the profile (masl)
     hts, hrs  -   Tx and Rx antenna heights above means sea level (m)
                   hts = htg + h(1), hrs = hrg + h(end)
     f         -   Frequency (GHz), not greater than 54 GHz

     Output parameters:
     Aosur     -   Attenuation due to oxygen (dB)
     Awsur     -   Attenuation due to water-vapour under non-rain conditions (dB)
    Awrsur    -   Attenuation due to water-vapour under rain conditions (dB)
     gamma_o  -   Specific attenuation due to oxygen (dB/km)
     gamma_w  -   Specific attenuation due to water-vapour non-rain conditions (dB/km)
     gamma_wr -   Specific attenuation due to water-vapour rain conditions (dB/km)
     rho_sur  -   Surface water-vapour content (g/m^3)

     Example:
     Aosur, Awsur, Awrsur, gamma_o, gamma_w, gamma_wr, rho_sur = gaseous_abs_surface(phi_me, phi_mn, h_mid, hts, hrs, dt, f)

       Rev   Date        Author                          Description
       -------------------------------------------------------------------------------
       v0    13JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
       v1    06SEP22     Ivica Stevaonvic, OFCOM         translated to python
    """
    # Obtain surface water-vapour density under non-rain conditions at the
    # midpoint of the path from the data file surfwv_50_fixed.txt

    surfwv_50_fixed = DigitalMaps["surfwv_50_fixed"]

    # Map Phime (-180, 180) to loncnt (0,360);

    phi_me1 = phi_me
    if phi_me < 0:
        phi_me1 = phi_me + 360

    # Find rho_sur from file surfwv_50_fixed.txt for the path mid-pint at phi_me1 (lon),
    # phi_mn (lat) - as a bilinear interpolation

    rho_sur = interp2(surfwv_50_fixed, phi_me1, phi_mn, 1.5, 1.5)

    h_sur = h_mid

    # Use equation (F.6.2) to calculate the sea-level specific attenuation due
    # to water vapour under non-rain conditions gamma_w

    gamma_o, gamma_w = specific_sea_level_attenuation(f, rho_sur, h_sur)

    # Use equation (F.5.1) to calculate the surface water-vapour density under
    # rain conditions rho_surr

    rho_surr = water_vapour_density_rain(rho_sur, h_sur)

    # Use equation (F.6.2) to calculate the sea-level specific attenuation due
    # to water vapour undr rain conditions gamma_wr

    _, gamma_wr = specific_sea_level_attenuation(f, rho_surr, h_sur)

    # Calculate the height for water-vapour density (F.2.1)

    h_rho = 0.5 * (hts + hrs)

    # Attenuation due to oxygen (F.2.2a)

    Aosur = gamma_o * dt * np.exp(-h_rho / 5000.0)

    # Attenuation due to water-vapour under non-rain conditions (F.2.2b)

    Awsur = gamma_w * dt * np.exp(-h_rho / 2000.0)

    # Attenuation due to water-vapour under non-rain conditions (F.2.2b)

    Awrsur = gamma_wr * dt * np.exp(-h_rho / 2000.0)

    return Aosur, Awsur, Awrsur, gamma_o, gamma_w, gamma_wr, rho_sur


def water_vapour_density_rain(rho_sur, h_sur):
    """water_vapour_density_rain Atmospheric water-vapour density in rain (Attachment F.5)
    This function computes atmosphoric water-vapour density in rain
    as defined in ITU-R P.2001-4 Attachment F.5

      Input parameters:
      rho_sur -   Surface water-vapour density under non-rain conditions (g/m^3)
      h_sur   -   Terrain height (masl)

      Output parameters:
      rho_surr-   Atmospheric water-vapour density in rain


      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    13JUL16     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevanovic, OFCOM         translated to python
    """
    rho_surr = rho_sur + 0.4 + 0.0003 * h_sur if h_sur <= 2600 else rho_sur + 5 * np.exp(-h_sur / 1800.0)

    return rho_surr


def specific_sea_level_attenuation(f, rho_sur, h_sur):
    """specific_sea_level_attenuation Specific sea-level attenuations (Attachment F.6)
    This function computes specific sea-level attenuations due to oxigen
    and water-vapour as defined in ITU-R P.2001-4 Attachment F.6
    The formulas are valid for frequencies not greater than 54 GHz.

      Input parameters:
      f       -   Frequency (GHz), not greater than 54 GHz
      rho_sur -   Surface water-vapour density under non-rain conditions (g/m^3)
      h_sur   -   Terrain height (masl)

      Output parameters:
      gamma_o -   Sea-level specific attenuation due to oxigen (dB/km)
      gamma_w -   Sea-level specific attenuation due to water vapour (dB/km)
      Rev   Date        Author                          Description
      -------------------------------------------------------------------------------
      v0    6SEP22     Ivica Stevanovic, OFCOM         Initial version MATLAB
      v1    06SEP22     Ivica Stevaonvic, OFCOM         translated to python
    """
    rho_sea = rho_sur * np.exp(h_sur / 2000)
    # Eq (F.6.2b)

    eta = 0.955 + 0.006 * rho_sea
    # Eq (F.6.2a)

    gamma_o = (7.2 / (f**2 + 0.34) + 0.62 / ((54 - f) ** 1.16 + 0.83)) * f**2 * 1e-3
    # Eq (F.6.1)

    gamma_w = (0.046 + 0.0019 * rho_sea + 3.98 * eta / ((f - 22.235) ** 2 + 9.42 * eta**2) * (1 + ((f - 22.0) / (f + 22.0)) ** 2)) * f**2 * rho_sea * 1e-4  # Eq (F.6.2)

    return gamma_o, gamma_w


def tropospheric_path(dt, hts, hrs, theta_e, theta_tpos, theta_rpos, ae, phi_re, phi_te, phi_rn, phi_tn, Re):
    """trophospheric path segments according to ITU-R P.2001-4

    This function computes tropospheric path segments as described in Section
    3.9 of Recommendation ITU-R P.2001-4

    Input parameters:
    dt        -   Path length (km)
    hts, hrs  -   Tx/Rx antenna heights above means sea level (m)
    theta_e   -   Angle subtended by d km at the center of a sphere of effective earth radius (rad)
    theta_tpos-   Interfering antenna horizon elevation angle limited to be positive (mrad)
    theta_rpos-   Interfered-with antenna horizon elevation angle limited to be positive (mrad)
                hts = htg + h(1)
    ae        -   median effective Earth's radius
    phi_re    -   Receiver longitude, positive to east (deg)
    phi_te    -   Transmitter longitude, positive to east (deg)
    phi_rn    -   Receiver latitude, positive to north (deg)
    phi_tn    -   Transmitter latitude, positive to north (deg)
    Re        -   Average Earth radius (km)

    Output parameters:
    d_tcv     -   Horizontal path length from transmitter to common volume (km)
    d_rcv     -   Horizontal path length from common volume to receiver (km)
    phi_cve   -   Longitude of the common volume
    phi_cvn   -   Latitude of the common volume
    h_cv      -   Height of the troposcatter common volume (masl)
    phi_tcve  -   Longitude of midpoint of the path segment from Tx to common volume
    phi_tcvn  -   Latitude of midpoint of the path segment from Tx to common volume
    phi_rcve  -   Longitude of midpoint of the path segment from common volume to Rx
    phi_rcvn  -   Latitude of midpoint of the path segment from common volumen to Rx
    """

    # Horizontal path lenght from transmitter to common volumne (3.9.1a)

    d_tcv = (dt * np.tan(0.001 * theta_rpos + 0.5 * theta_e) - 0.001 * (hts - hrs)) / (np.tan(0.001 * theta_tpos + 0.5 * theta_e) + np.tan(0.001 * theta_rpos + 0.5 * theta_e))

    # Limit d_tcv such that 0 <= dtcv <= dt

    d_tcv = np.clip(d_tcv, 0, dt)

    # Horizontal path length from common volume to receiver (3.9.1b)

    d_rcv = dt - d_tcv

    # Calculate the longitude and latitude of the common volumne from the
    # transmitter and receiver longitudes and latitudes using the great circle
    # path method of Attachment H by seting d_pnt = d_tcv

    phi_cve, phi_cvn, _, _ = great_circle_path(phi_re, phi_te, phi_rn, phi_tn, Re, d_tcv)

    # Calculate the height of the troposcatter common volume (3.9.2)

    h_cv = hts + 1000 * d_tcv * np.tan(0.001 * theta_tpos) + 1000 * d_tcv**2 / (2 * ae)

    # Calculate the longitude and latitude of the midpoint of hte path segment
    # from transmitter to common volume by setting dpnt = 0.5dtcv

    d_pnt = 0.5 * d_tcv

    phi_tcve, phi_tcvn, _, _ = great_circle_path(phi_re, phi_te, phi_rn, phi_tn, Re, d_pnt)

    # Calculate the longitude and latitude of the midpoint of the path segment
    # from receiver to common volume by setting dpnt = dt - 0.5drcv

    d_pnt = dt - 0.5 * d_rcv

    phi_rcve, phi_rcvn, _, _ = great_circle_path(phi_re, phi_te, phi_rn, phi_tn, Re, d_pnt)

    return d_tcv, d_rcv, phi_cve, phi_cvn, h_cv, phi_tcve, phi_tcvn, phi_rcve, phi_rcvn


def smooth_earth_heights(d, h, hts, hrs, ae, lam):
    """smooth_earth_heights smooth-Earth effective antenna heights according to ITU-R P.2001-4
    This function derives smooth-Earth effective antenna heights according to
    Sections 3.7 and 3.8 of Recommendation ITU-R P.2001-4

    Input parameters:
    d         -   vector of terrain profile distances from Tx [0,dtot] (km)
    h         -   vector of terrain profile heights amsl (m)
    hts, hrs  -   Tx and Rx antenna heights above means sea level (m)
                hts = htg + h(1), hrs = hrg + h(end)
    ae        -   median effective Earth's radius
    lam       -   wavelength (m)

    Output parameters:

    theta_t      -   Interfering antenna horizon elevation angle (mrad)
    theta_r      -   Interfered-with antenna horizon elevation angle (mrad)
    theta_tpos   -   Interfering antenna horizon elevation angle limited to be positive (mrad)
    theta_rpos   -   Interfered-with antenna horizon elevation angle limited to be positive (mrad)
    dlt          -   Tx antenna horizon distance (km)
    dlr          -   Rx antenna horizon distance (km)
    lt           -   Index i in the path profile for which dlt=d(lt)
    lr           -   Index i in tha path profile for which dlr = d(lr)
    hstip, hrip  -   Initial smooth-surface height at Tx/Rx
    hstipa, hripa-   Smooth surface height at Tx/Rx not exceeding ground level
    htea, htea   -   Effective Tx and Rx antenna heigts above the smooth-Earth surface amsl for anomalous propagation (m)
    mses         -   Smooth surface slope (m/km)
    hm           -   The terrain roughness parameter (m)
    hst, hsr     -   Heights of the smooth surface at the Tx and Rx ends of the paths
    htep, hrep   -   Effective Tx and Rx antenna heights for the
                    spherical-earth and the smooth-pofile version of the
                    Bullingtong diffraction model (m)
    FlagLos50    -   1 = Line-of-sight 50% time, 0 = otherwise

    Example
    theta_t, theta_r, theta_tpos, theta_rpos, dlt, dlr, lt, lr, hstip, hsrip, hstipa, hsripa, htea, hrea, mses, hm, hst, hsr, htep, hrep, FlagLos50 = smooth_earth_heights(d, h, hts, hrs, ae, lam)

    """
    n = len(d)

    dtot = d[-1]

    # Tx and Rx antenna heights above mean sea level amsl (m)

    ## 3.7 Path classification and terminal horizon parameters

    # Highest elevation angle to an intermediate profile point, relative to the
    # horizontal at the transmitter (3.7.1)

    ii = range(1, n - 1)

    theta = (h[ii] - hts) / d[ii] - 500 * d[ii] / ae
    theta_tim = max(theta)

    # Elevation angle of the receiver as viewed by the transmitter, assuming a
    # LoS path (3.7.2)

    theta_tr = (hrs - hts) / dtot - 500 * dtot / ae

    if theta_tim < theta_tr:  # path is LoS
        FlagLos50 = 1
        nu = (h[ii] + 500 * d[ii] * (dtot - d[ii]) / ae - (hts * (dtot - d[ii]) + hrs * d[ii]) / dtot) * np.sqrt(0.002 * dtot / (lam * d[ii] * (dtot - d[ii])))  # Eq (3.7.3)

        numax = max(nu)

        (kindex,) = np.where(nu == numax)
        lt = kindex[-1] + 1  # in order to map back to path d indices, as theta takes path indices 2 to n-1,
        dlt = d[lt]  # Eq (3.7.4a)
        dlr = dtot - dlt  # Eq (3.7.4b)
        lr = lt  # Eq (3.7.4d)

        theta_t = theta_tr  # Eq (3.7.5a)
        theta_r = -theta_tr - 1000 * dtot / ae  # Eq (3.7.5b)

    else:
        FlagLos50 = 0
        # Transmitter hoizon distance and profile index of the horizon point (3.7.6)

        theta_ti = (h[ii] - hts) / d[ii] - 500 * d[ii] / ae
        (kindex,) = np.where(theta_ti == theta_tim)
        lt = kindex[-1] + 1  # in order to map back to path d indices, as theta takes path indices 2 to n-1,
        dlt = d[lt]  # Eq (3.7.6a)

        # Transmitter horizon elevation angle reltive to its local horizontal (3.7.7)
        theta_t = theta_tim

        # Find the heighest elevation angle to an intermediate profile point,
        # relative to the horizontal at the receiver (3.7.8)

        theta_ri = (h[ii] - hrs) / (dtot - d[ii]) - 500 * (dtot - d[ii]) / ae

        theta_rim = max(theta_ri)
        (kindex,) = np.where(theta_ri == theta_rim)
        lr = kindex[-1] + 1  # in order to map back to path d indices, as theta takes path indices 2 to n-1,
        dlr = dtot - d[lr]  # Eq (3.7.9)

        # receiver horizon elevatio nangle relative to its local horizontal
        theta_r = theta_rim  # Eq (3.7.10)

    # Calculate the horizon elevation angles limited such that they are
    # positive

    theta_tpos = max(theta_t, 0)  # Eq (3.7.11a)
    theta_rpos = max(theta_r, 0)  # Eq (3.7.11b)

    ## 3.8 Effective heights and path roughness parameter

    ii = np.arange(1,n)
    v1 = ((d[ii] - d[ii - 1]) * (h[ii] + h[ii - 1])).sum()  # Eq (85)
    v2 = ((d[ii] - d[ii - 1]) * (h[ii] * (2 * d[ii] + d[ii - 1]) + h[ii - 1] * (d[ii] + 2 * d[ii - 1]))).sum()  # Eq (86)

    hstip = (2 * v1 * dtot - v2) / dtot**2  # Eq (3.8.3a)
    hsrip = (v2 - v1 * dtot) / dtot**2  # Eq (3.8.3b)

    # Smooth-sruface heights limited not to exceed ground leve at either Tx or Rx

    hstipa = min(hstip, h[0])
    # Eq (3.8.4a)
    hsripa = min(hsrip, h[-1])
    # Eq (3.8.4b)

    # The slope of the least-squares regression fit (3.8.5)

    mses = (hsripa - hstipa) / dtot

    # effective heights of Tx and Rx antennas above the smooth surface (3.8.6)

    htea = hts - hstipa
    hrea = hrs - hsripa

    # Path roughness parameter (3.8.7)

    ii = range(lt, lr + 1)

    hm = max(h[ii] - (hstipa + mses * d[ii]))

    # Smooth-surface heights for the diffraction model

    HH = h - (hts * (dtot - d) + hrs * d) / dtot  #  Eq (3.8.8d)

    hobs = max(HH[1:-1])  # Eq (3.8.8a)

    alpha_obt = max(HH[1:-1] / d[1:-1])  # Eq (3.8.8b)

    alpha_obr = max(HH[1:-1] / (dtot - d[1:-1]))  # Eq (3.8.8c)

    # Calculate provisional values for the Tx and Rx smooth surface heights

    gt = alpha_obt / (alpha_obt + alpha_obr)  # Eq (3.8.9e)
    gr = alpha_obr / (alpha_obt + alpha_obr)  # Eq (3.8.9f)

    if hobs <= 0:
        hst = hstip  # Eq (3.8.9a)
        hsr = hsrip  # Eq (3.8.9b)
    else:
        hst = hstip - hobs * gt  # Eq (3.8.9c)
        hsr = hsrip - hobs * gr  # Eq (3.8.9d)

    # calculate the final values as required by the diffraction model

    if hst >= h[0]:
        hst = h[0]  # Eq (3.8.10a)

    if hsr > h[-1]:
        hsr = h[-1]  # Eq (3.8.10b)

    # The terminal effective heigts for the ducting/layer-reflection model

    htep = hts - hst  # Eq (3.8.11a)
    hrep = hrs - hsr  # Eq (3.8.11b)

    return theta_t, theta_r, theta_tpos, theta_rpos, dlt, dlr, lt, lr, hstip, hsrip, hstipa, hsripa, htea, hrea, mses, hm, hst, hsr, htep, hrep, FlagLos50


def interp2(matrix_map, lon, lat, lon_spacing, lat_spacing):
    """
    Bi-linear interpolation of data contained in 2D matrix map at point (lon,lat)
    It assumes that the grid is rectangular with spacing of 1.5 deg in both lon and lat
    It assumes that lon goes from 0 to 360 deg and lat goes from 90 to -90 deg
    """

    latitudeOffset = 90.0 - lat
    longitudeOffset = lon
    
    if (lon < 0.0):
        longitudeOffset = lon + 360.0

    sizeY, sizeX = matrix_map.shape

    latitudeIndex = int(latitudeOffset / lat_spacing)
    longitudeIndex = int(longitudeOffset / lon_spacing)

    latitudeFraction = (latitudeOffset / lat_spacing) - latitudeIndex
    longitudeFraction = (longitudeOffset / lon_spacing) - longitudeIndex

    value_ul = matrix_map[latitudeIndex][longitudeIndex]
    value_ur = matrix_map[latitudeIndex][(longitudeIndex + 1) % sizeX]
    value_ll = matrix_map[(latitudeIndex + 1) % sizeY][longitudeIndex]
    value_lr = matrix_map[(latitudeIndex + 1) % sizeY][(longitudeIndex + 1) % sizeX]

    interpolatedHeight1 = (longitudeFraction * (value_ur - value_ul)) + value_ul
    interpolatedHeight2 = (longitudeFraction * (value_lr - value_ll)) + value_ll
    interpolatedHeight3 = latitudeFraction * (interpolatedHeight2 - interpolatedHeight1) + interpolatedHeight1

    return interpolatedHeight3


def path_fraction(d, zone, zone_r):
    """
    path_fraction Path fraction belonging to a given zone_r
    omega = path_fraction(d, zone, zone_r)
    This function computes the path fraction belonging to a given zone_r
    of the great-circle path (km)

    Input arguments:
    d       -   vector of distances in the path profile
    zone    -   vector of zones in the path profile
    zone_r  -   reference zone for which the fraction is computed

    Output arguments:
    omega   -   path fraction belonging to the given zone_r

    Example:
    omega = path_fraction(d, zone, zone_r)

    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    02FEB16     Ivica Stevanovic, OFCOM         First implementation in matlab
    v1    11NOV22     Ivica Stevanovic, OFCOM         Corrected a bug in the second if clause (suggested by Martin-Pierre Lussier @mplussier)   
    """
    dm = 0

    start, stop = find_intervals((zone == zone_r))

    n = len(start)

    for i in range(0, n):
        delta = 0
        if d[stop[i]] < d[-1]:
            delta = delta + (d[stop[i] + 1] - d[stop[i]]) / 2.0

        if d[start[i]] > 0:
            delta = delta + (d[start[i]] - d[start[i] - 1]) / 2.0

        dm = dm + d[stop[i]] - d[start[i]] + delta

    omega = dm / (d[-1] - d[0])

    return omega


def great_circle_path(Phire, Phite, Phirn, Phitn, Re, dpnt):
    """
    great_circle_path Great-circle path calculations according to Attachment H
    This function computes the great-circle intermediate points on the
    radio path as defined in ITU-R P.2001-4 Attachment H

        Input parameters:
        Phire   -   Receiver longitude, positive to east (deg)
        Phite   -   Transmitter longitude, positive to east (deg)
        Phirn   -   Receiver latitude, positive to north (deg)
        Phitn   -   Transmitter latitude, positive to north (deg)
        Re      -   Average Earth radius (km)
        dpnt    -   Distance from the transmitter to the intermediate point (km)

        Output parameters:
        Phipnte -   Longitude of the intermediate point (deg)
        Phipntn -   Latitude of the intermediate point (deg)
        Bt2r    -   Bearing of the great-circle path from Tx towards the Rx (deg)
        dgc     -   Great-circle path length (km)

        Example:
        [Bt2r, Phipnte, Phipntn, dgc] = great_circle_path(Phire, Phite, Phirn, Phitn, Re, dpnt)

        Rev   Date        Author                          Description
        -------------------------------------------------------------------------------
        v0    05SEP22     Ivica Stevanovic, OFCOM         Initial version
    """
    ## H.2 Path length and bearing

    # Difference (deg) in longitude between the terminals (H.2.1)

    Dlon = Phire - Phite

    # Calculate quantity r (H.2.2)

    r = sind(Phitn) * sind(Phirn) + cosd(Phitn) * cosd(Phirn) * cosd(Dlon)

    # Calculate the path length as the angle subtended at the center of
    # average-radius Earth (H.2.3)

    Phid = np.arccos(r)  # radians

    # Calculate the great-circle path length (H.2.4)

    dgc = Phid * Re  # km

    # Calculate the quantity x1 (H.2.5a)

    x1 = sind(Phirn) - r * sind(Phitn)

    # Calculate the quantity y1 (H.2.5b)

    y1 = cosd(Phitn) * cosd(Phirn) * sind(Dlon)

    # Calculate the bearing of the great-circle path for Tx to Rx (H.2.6)

    Bt2r = Phire if abs(x1) < 1e-9 and abs(y1) < 1e-9 else atan2d(y1, x1)

    ## H.3 Calculation of intermediate path point

    # Calculate the distance to the point as the angle subtended at the center
    # of average-radius Earth (H.3.1)

    Phipnt = dpnt / Re  # radians

    # Calculate quantity s (H.3.2)

    s = sind(Phitn) * np.cos(Phipnt) + cosd(Phitn) * np.sin(Phipnt) * cosd(Bt2r)

    # The latitude of the intermediate point is now given by (H.3.3)

    Phipntn = np.arcsin(s) * 180.0 / np.pi  # degs

    # Calculate the quantity x2 (H.3.4a)

    x2 = np.cos(Phipnt) - s * sind(Phitn)

    # Calculate the quantity y2 (H.3.4b)

    y2 = cosd(Phitn) * np.sin(Phipnt) * sind(Bt2r)

    # Calculate the longitude of the intermediate point Phipnte (H.3.5)

    Phipnte = Bt2r if x2 < 1e-9 and y2 < 1e-9 else Phite + atan2d(y2, x2)

    return Phipnte, Phipntn, Bt2r, dgc


def find_intervals(series):
    """
    find_intervals Find all intervals with consecutive 1's
    [k1, k2] = find_intervals(series)
    This function finds all 1's intervals, namely, the indices when the
    intervals start and where they end

    For example, for the input indices
        0 0 1 1 1 1 0 0 0 1 1 0 0
    this function will give back
        k1 = 3, 10
        k2 = 6, 11

    Input arguments:
    indices -   vector containing zeros and ones

    Output arguments:
    k1      -   vector of start-indices of the found intervals
    k2      -   vector of end-indices of the found intervals

    Example:
    [k1, k2] = find_intervals(indices)

    Rev   Date        Author                          Description
    -------------------------------------------------------------------------------
    v0    18MAR22     Ivica Stevanovic, OFCOM         First implementation in matlab

    """
    k1 = []
    k2 = []
    series_int = 1 * series
    # make sure series is  is a row vector

    # if (size(series,1) > 1):
    #    series = series.'

    if max(series_int) == 1:
        (k1,) = np.where(np.diff(np.append(0, series_int)) == 1)
        (k2,) = np.where(np.diff(np.append(series_int, 0)) == -1)

    return k1, k2


def sind(x):
    return np.sin(x * np.pi / 180.0)


def cosd(x):
    return np.cos(x * np.pi / 180.0)


def atan2d(y, x):
    return np.arctan2(y, x) * 180.0 / np.pi
