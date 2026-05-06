const STEAM_OPENID_URL = "https://steamcommunity.com/openid/login";
const OPENID_NS = "http://specs.openid.net/auth/2.0";
const STEAM_CLAIMED_ID_PREFIX = "https://steamcommunity.com/openid/id/";

export function buildSteamOpenIdUrl(origin: string, callbackPath: string) {
  const callbackUrl = new URL(callbackPath, origin);
  const realm = new URL(origin);
  realm.pathname = "/";
  realm.search = "";
  realm.hash = "";

  const params = new URLSearchParams({
    "openid.ns": OPENID_NS,
    "openid.mode": "checkid_setup",
    "openid.return_to": callbackUrl.toString(),
    "openid.realm": realm.toString(),
    "openid.identity": `${OPENID_NS}/identifier_select`,
    "openid.claimed_id": `${OPENID_NS}/identifier_select`,
  });

  return `${STEAM_OPENID_URL}?${params.toString()}`;
}

export async function verifySteamOpenId(searchParams: URLSearchParams) {
  const params = new URLSearchParams(searchParams);
  params.set("openid.mode", "check_authentication");

  const response = await fetch(STEAM_OPENID_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
    cache: "no-store",
  });

  const text = await response.text();
  return response.ok && text.includes("is_valid:true");
}

export function extractSteamId(claimedId: string | null) {
  if (!claimedId || !claimedId.startsWith(STEAM_CLAIMED_ID_PREFIX)) {
    return null;
  }

  const steamId = claimedId.slice(STEAM_CLAIMED_ID_PREFIX.length).trim();
  return /^\d+$/.test(steamId) ? steamId : null;
}
