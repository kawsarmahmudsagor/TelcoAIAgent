"""The five demo personas, keyed by msisdn (subscriber ids are random at seed
time). Shared by the seed and the portal's persona login."""

SAMIHA = "01712342841"
RAFI = "01812347392"
NUSRAT = "01912345501"
TANVIR = "01612341109"
FARHANA = "01512346620"

# msisdn -> one-line headline, in seed order.
PERSONA_HEADLINES: dict[str, str] = {
    SAMIHA: "Pack expiring in 3 days",
    RAFI: "Low balance, a recharge pending",
    NUSRAT: "Postpaid bill due",
    TANVIR: "Low data in a congested area",
    FARHANA: "Lots of reward points, one open case",
}
