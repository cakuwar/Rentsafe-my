// Real search results for Vigor Properties Sdn Bhd (2026-10-04). The first
// implementation scored them 5 points; all four are false positives:
//   [0] a property reel mentioning "risiko scam"
//   [1] the company's own notice that someone is impersonating its agents
//       (冒充 appears only in the Facebook URL slug)
//   [2] an ad saying it is not a scam
//   [3] a reel where the company is a tagged sponsor and "scam" is another topic
export const VIGOR_META = {
  phone: "014-793 9923",
  agentName: "Emilie Yip",
  company: "Vigor Properties Sdn Bhd",
  identitySource: "form",
};

export const VIGOR_RESULTS = [
  {
    title: "𝐓𝐀𝐊𝐔𝐓 𝐓𝐄𝐑𝐒𝐈𝐋𝐀𝐏 𝐋𝐀𝐍𝐆𝐊𝐀𝐇? 𝐓𝐄𝐍𝐆𝐎𝐊 𝐍𝐈 𝐃𝐔𝐋𝐔! ...",
    link: "https://www.instagram.com/reel/DZsN7foTkQJ/",
    snippet: "... VIGOR PROPERTIES SDN BHD MALAY WING SUBSCRIBE SPARK . RECRUIT ... Daripada tersalah langkah, kena hadap risiko scam, atau pening nak ...",
  },
  {
    title: "⚠️ VIGOR PROPERTIES 重要公告近期本公司接获客户 ...",
    link: "https://www.facebook.com/61567073039339/posts/%EF%B8%8F-vigor-properties-%E9%87%8D%E8%A6%81%E5%85%AC%E5%91%8A%E8%BF%91%E6%9C%9F%E6%9C%AC%E5%85%AC%E5%8F%B8%E6%8E%A5%E8%8E%B7%E5%AE%A2%E6%88%B7%E4%B8%BE%E6%8A%A5%E5%8F%91%E7%8E%B0%E6%9C%89%E4%BA%BA%E7%96%91%E4%BC%BC%E5%86%92%E5%85%85-vigor-properties-%E6%88%BF%E5%9C%B0%E4%BA%A7%E4%B8%AD%E4%BB%8B%E8%BA%AB%E4%BB%BD%E4%B8%8E%E5%AE%A2%E6%88%B7%E6%8E%A5%E6%B4%BD%E8%AF%A5%E4%BA%BA%E5%A3%AB%E5%B9%B6%E9%9D%9E%E6%9C%AC%E5%85%AC%E5%8F%B8/122219759420569101/",
    snippet: "VIGOR PROPERTIES SDN BHD. 9w. Vigor Properties HQ. Ryt bank +603-5115 5115. National scam centre 997 Shall call this report scammer. 9w. Normala ...",
  },
  {
    title: "𝐁𝐄𝐓𝐔𝐋 𝐊𝐄 𝐌𝐎𝐃𝐀𝐋 𝐑𝐌299 𝐁𝐎𝐋𝐄𝐇 𝐁𝐄𝐋𝐈 𝐑𝐔𝐌𝐀𝐇!? ...",
    link: "https://www.instagram.com/reel/Dbxpyr3PXT2/",
    snippet: "... scam, bukan fake news. Beli rumah sekarang takde la stress mana ... PAKAR HARTANAH ANDA IN PARTNERSHIP WITH: VIGOR PROPERTIES SDN BHD BANK ISLAM ...",
  },
  {
    title: "How much does it cost time okay football in Malaysia ⚽️🇲🇾 ...",
    link: "https://www.instagram.com/reel/Dac0h5ANFmm/",
    snippet: "Why are people calling it a scam? That's ... MALAYSIA CREATOR VIGOR PROPERTIES SDN BHD MALAY ... My first stop was NZ Curry House on Jalan Ampang ...",
  },
];

// The same four texts served from a forum, so that rule 4 (company hits on
// social media are context) does not apply and they reach the judge.
export const VIGOR_ON_FORUM = VIGOR_RESULTS.map((result, index) => ({
  ...result,
  link: `https://forum.lowyat.net/topic/vigor-${index}`,
}));
