// Real search results from the first 10-case run (2026-10-10). Bank account
// and IC numbers in the snippets are masked; they play no part in matching.

// Case 3. Both posts carry the phone, but Google returned them for the NAME
// query only. The first run filed them under the name, and lost the PDRM post
// because "TIDAK" at the end of its title negated "PENIPUAN" in its snippet.
export const FUAD_META = {
  phone: "01169340728",
  agentName: "mohd noor fuad bin haji jamaludin",
  identitySource: "form",
};

export const FUAD_NAME_RESULTS = [
  {
    title: "Hati2 guys ade taktik terbaru scammer",
    link: "https://www.facebook.com/groups/1221989615410645/posts/2039318653677733/",
    snippet: "PENIPUAN RUMAH SEWA!!! Taman Segar Flat.. Hati² gais... No tel : 01169340728 No acc: XXXXXXXXXXXXXXXX Nama :mohd noor fuad bin haji jamaludin ...",
  },
  {
    title: "WANITA DITAHAN DISYAKI TAWAR RUMAH TIDAK ...",
    link: "https://www.facebook.com/pdrmsiaofficial/posts/wanita-ditahan-disyaki-tawar-rumah-tidak-wujudseorang-promoter-wanita-sebuah-sya/2030210463655917/",
    snippet: "PENIPUAN RUMAH SEWA!!! Taman Segar Flat.. Hati² gais... No tel : 01169340728 No acc: XXXXXXXXXXXXXXXX Nama :mohd noor fuad bin haji jamaludin ...",
  },
];

// Case 7. The name appears in a scam post, but the agent's phone does not:
// it may be a different person with the same name.
export const RAZALI_META = {
  phone: "0135796895",
  agentName: "Syed Ahmad Razali",
  identitySource: "form",
};

export const RAZALI_NAME_RESULTS = [
  {
    title: "Scammer Alert!! Scammer Alert!! Hasliza Bt Harun !! ...",
    link: "https://www.facebook.com/groups/2009835379336118/posts/4124272134559088/",
    snippet: "Tapi dorang pun SCAMMER jugak. Bsn ( Syed Ahmad Razali bin Wan Yusof ) XXXXXXXXXXXXXXXX XXXXXXXXXXXX ( Syed Ahmad Razali bin Wan Yusof ) X ...",
  },
];
