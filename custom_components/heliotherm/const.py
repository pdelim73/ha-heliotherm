"""Constants and the parameter table for the Heliotherm integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DOMAIN = "heliotherm"
MANUFACTURER = "Heliotherm"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SP_INTERVAL = "sp_interval"

DEFAULT_PORT = 4196
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_SP_INTERVAL = 10  # read SP (config) parameters every Nth cycle


@dataclass(frozen=True)
class HtParam:
    """One heat pump data point."""

    key: str
    name: str
    ptype: str          # "MP" (measurement) or "SP" (setting)
    nr: int
    dtype: str          # "BOOL" | "INT" | "FLOAT"
    unit: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None


# Fast-changing measurements — polled every cycle.
MP_PARAMS: tuple[HtParam, ...] = (
    HtParam("temp_aussen", "Temp. Aussen", "MP", 0, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_aussen_verzoegert", "Temp. Aussen verzoegert", "MP", 1, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_brauchwasser", "Temp. Brauchwasser", "MP", 2, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_vorlauf", "Temp. Vorlauf", "MP", 3, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_ruecklauf", "Temp. Ruecklauf", "MP", 4, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_eq_eintritt", "Temp. EQ_Eintritt", "MP", 6, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_eq_austritt", "Temp. EQ_Austritt", "MP", 7, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_sauggas", "Temp. Sauggas", "MP", 9, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_frischwasser_istwert", "Temp. Frischwasser_Istwert", "MP", 11, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_verdampfung", "Temp. Verdampfung", "MP", 12, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_kondensation", "Temp. Kondensation", "MP", 13, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("temp_heissgas", "Temp. Heissgas", "MP", 15, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("niederdruck_bar", "Niederdruck (bar)", "MP", 20, "FLOAT", "bar", SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
    HtParam("hochdruck_bar", "Hochdruck (bar)", "MP", 21, "FLOAT", "bar", SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
    HtParam("heizkreispumpe", "Heizkreispumpe", "MP", 22, "BOOL", None, None, None),
    HtParam("eq_pumpe_ventilator", "EQ Pumpe (Ventilator)", "MP", 24, "BOOL", None, None, None),
    HtParam("warmwasservorrang", "Warmwasservorrang", "MP", 25, "BOOL", None, None, None),
    HtParam("zirkulationspumpe_ww", "Zirkulationspumpe WW", "MP", 29, "BOOL", None, None, None),
    HtParam("verdichter", "Verdichter", "MP", 30, "BOOL", None, None, None),
    HtParam("stoerung", "Stoerung", "MP", 31, "BOOL", None, None, None),
    HtParam("hauptschalter", "Hauptschalter", "MP", 36, "BOOL", None, None, None),
    HtParam("fws_stroemungsschalter", "FWS Stroemungsschalter", "MP", 38, "BOOL", None, None, None),
    HtParam("bsz_verdichter_schaltungen", "BSZ Verdichter Schaltungen", "MP", 41, "INT", None, None, SensorStateClass.TOTAL_INCREASING),
    HtParam("frischwasserpumpe", "Frischwasserpumpe", "MP", 50, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("verdichteranforderung", "Verdichteranforderung", "MP", 56, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("hkr_sollwert", "HKR_Sollwert", "MP", 57, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),)

# Configuration values — polled every SP_INTERVAL cycles.
SP_PARAMS: tuple[HtParam, ...] = (
    HtParam("liegenschaft", "Liegenschaft", "SP", 3, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("wp_system", "WP_System", "SP", 4, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("ww_type", "WW Type", "SP", 5, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("fws_type", "FWS Type", "SP", 6, "BOOL", None, None, None),
    HtParam("puffer_type", "Puffer Type", "SP", 7, "BOOL", None, None, None),
    HtParam("verdichter_status", "Verdichter_Status", "SP", 10, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("verdichter_laeuft_seit", "Verdichter laeuft seit", "SP", 11, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("verdichter_einschaltverz_sec", "Verdichter Einschaltverz.(sec)", "SP", 12, "INT", "s", SensorDeviceClass.DURATION, SensorStateClass.MEASUREMENT),
    HtParam("betriebsart", "Betriebsart", "SP", 13, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("hkr_soll_raum", "HKR Soll_Raum", "SP", 69, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("hkr_aufheiztemp_k", "HKR Aufheiztemp. (K)", "SP", 71, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("hkr_absenktemp_k", "HKR Absenktemp. (K)", "SP", 72, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("hkr_heizgrenze", "HKR Heizgrenze", "SP", 76, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("hkr_rlt_soll_ohg_heizkurve", "HKR RLT Soll_oHG (Heizkurve)", "SP", 80, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("hkr_rlt_soll_0_heizkurve", "HKR RLT Soll_0 (Heizkurve)", "SP", 81, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("hkr_rlt_soll_uhg_heizkurve", "HKR RLT Soll_uHG (Heizkurve)", "SP", 82, "FLOAT", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    HtParam("ww_normaltemp", "WW Normaltemp.", "SP", 83, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("ww_hysterese_normaltemp", "WW Hysterese Normaltemp.", "SP", 84, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("ww_minimaltemp", "WW Minimaltemp.", "SP", 85, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("ww_hysterese_minimaltemp", "WW Hysterese Minimaltemp.", "SP", 86, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("bsz_hkp_betriebsstunden", "BSZ HKP Betriebsstunden", "SP", 153, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_hkp_schaltung", "BSZ HKP Schaltung", "SP", 155, "INT", None, None, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_eq_betriebsstunden", "BSZ EQ Betriebsstunden", "SP", 162, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_eq_schaltungen", "BSZ EQ Schaltungen", "SP", 164, "INT", None, None, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_wwv_betriebsstunden", "BSZ WWV Betriebsstunden", "SP", 165, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_wwv_schaltungen", "BSZ WWV Schaltungen", "SP", 167, "INT", None, None, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_zipww_betriebsstunden", "BSZ ZIPWW Betriebsstunden", "SP", 168, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_zipww_schaltungen", "BSZ ZIPWW Schaltungen", "SP", 170, "INT", None, None, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_verdichter_betriebsst_ww", "BSZ Verdichter Betriebsst. WW", "SP", 171, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_verdichter_betriebsst_hkr", "BSZ Verdichter Betriebsst. HKR", "SP", 172, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_verdichter_betriebsst_ges", "BSZ Verdichter Betriebsst. ges", "SP", 173, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("bsz_verdichter_akt_laufzeit", "BSZ Verdichter akt. Laufzeit", "SP", 174, "INT", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING),
    HtParam("mkr2_aktiviert", "MKR2 Aktiviert", "SP", 222, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("energiezaehler", "Energiezaehler", "SP", 263, "INT", None, None, SensorStateClass.MEASUREMENT),
    HtParam("bsz_verdichter_schaltung_ww", "BSZ Verdichter Schaltung WW", "SP", 375, "INT", None, None, SensorStateClass.TOTAL_INCREASING),)

ALL_PARAMS: tuple[HtParam, ...] = MP_PARAMS + SP_PARAMS
PARAMS_BY_KEY: dict[str, HtParam] = {p.key: p for p in ALL_PARAMS}
