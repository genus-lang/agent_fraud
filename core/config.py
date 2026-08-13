MAX_PROVIDER_CAP = 100  # upper safety cap to avoid runaway loops
TOOL_TIMEOUT = 10       # seconds per HTTP request (Google, Socrata)
DCFS_TIMEOUT = 30       # IL DCFS is a slow government site

# Cook County Socrata endpoints (no auth required)
_COOK_ADDR_URL = "https://datacatalog.cookcountyil.gov/resource/3723-97qp.json"
_COOK_RES_URL = "https://datacatalog.cookcountyil.gov/resource/x54s-btds.json"
_COOK_COMMERCIAL_URL = "https://datacatalog.cookcountyil.gov/resource/csik-bsws.json"
_COOK_ASSESSED_URL = "https://datacatalog.cookcountyil.gov/resource/uzyt-m557.json"

# Illinois DCFS provider lookup
_IL_DCFS_URL = "https://sunshine.dcfs.illinois.gov/Content/Licensing/Daycare/ProviderLookup.aspx"
