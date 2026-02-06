package fetcher

var pizzaPlaces = []struct {
	Name    string
	PlaceID string
	Address string
}{
	{Name: "Domino's Pizza", PlaceID: "ChIJN1t_tDeuEmsRUsoyG83frY4", Address: "Pentagon City"},
	{Name: "Papa John's", PlaceID: "ChIJP3Sa8ziYEmsRUKgyFmh9AQM", Address: "Near Pentagon"},
	{Name: "Pizza Hut", PlaceID: "ChIJrTLr-GyuEmsRBfy61i59si0", Address: "Pentagon Area"},
}

var alertKeywords = []string{
	"strike", "attack", "military", "bomb", "missile", "war", "imminent", "troops", "forces",
}

var iranKeywords = []string{
	"iran", "tehran", "persian gulf", "strait of hormuz",
}

var strikeKeywords = []string{
	"strike", "attack", "bomb", "military action",
}

var negativeKeywords = []string{
	" not ", "won't", "will not", "doesn't", "does not",
}

var tankerPrefixes = []string{
	"IRON", "SHELL", "TEXAN", "ETHYL", "PEARL", "ARCO", "ESSO", "MOBIL", "GULF", "TOPAZ",
	"PACK", "DOOM", "TREK", "REACH",
	"EXXON", "TEXACO", "OILER", "OPEC", "PETRO",
	"TOGA", "DUCE", "FORCE", "GUCCI", "XTNDR", "SPUR", "TEAM", "QUID",
	"BOLT", "BROKE", "BROOM", "BOBBY", "BOBBIE", "BODE", "CONIC", "MAINE", "BRIG", "ARTLY", "BANKER", "BRUSH",
	"ARRIS",
	"GOLD", "BLUE", "CLEAN", "VINYL",
}

const (
	usafHexStart = 0xAE0000
	usafHexEnd   = 0xAE7FFF
)

var rssFeeds = []string{
	"https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
	"https://www.aljazeera.com/xml/rss/all.xml",
}

var months = []string{
	"january", "february", "march", "april", "may", "june",
	"july", "august", "september", "october", "november", "december",
}

const (
	cloudflareRadarBaseURL  = "https://api.cloudflare.com/client/v4/radar"
	cloudflareRadarLocation = "IR"
)
