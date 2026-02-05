package fetcher

import (
	"encoding/xml"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

// RSS feed structures
type rssRoot struct {
	XMLName xml.Name   `xml:"rss"`
	Channel rssChannel `xml:"channel"`
}

type rssChannel struct {
	Items []rssItem `xml:"item"`
}

type rssItem struct {
	Title       string `xml:"title"`
	Description string `xml:"description"`
}

// Atom feed structures
type atomFeed struct {
	XMLName xml.Name    `xml:"feed"`
	Entries []atomEntry `xml:"entry"`
}

type atomEntry struct {
	Title   string `xml:"title"`
	Summary string `xml:"summary"`
}

func (f *Fetcher) fetchNews() (model.NewsData, map[string]any, error) {
	slog.Info("fetching news intelligence")

	var allArticles []map[string]any
	alertCount := 0

	for _, feedURL := range rssFeeds {
		slog.Info("fetching RSS feed", "url", feedURL)

		req, err := http.NewRequest("GET", feedURL, nil)
		if err != nil {
			slog.Warn("news request create failed", "url", feedURL, "error", err)
			continue
		}
		req.Header.Set("User-Agent", "Mozilla/5.0 (compatible; StrikeRadar/1.0)")

		resp, err := f.client.Do(req)
		if err != nil {
			slog.Warn("news fetch failed", "url", feedURL, "error", err)
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			slog.Warn("news read body failed", "url", feedURL, "error", err)
			continue
		}
		if resp.StatusCode != 200 {
			slog.Warn("news feed error", "url", feedURL, "status", resp.StatusCode)
			continue
		}

		// Try RSS first, then Atom
		items := parseRSS(body)
		if len(items) == 0 {
			items = parseAtom(body)
		}

		for _, item := range items {
			combined := strings.ToLower(item.title + " " + item.desc)
			if !containsAny(combined, iranKeywords) {
				continue
			}
			isAlert := containsAny(combined, alertKeywords)
			if isAlert {
				alertCount++
			}
			title := item.title
			if len(title) > 100 {
				title = title[:100]
			}
			allArticles = append(allArticles, map[string]any{
				"title":    title,
				"is_alert": isAlert,
			})
		}
	}

	// Deduplicate
	seen := make(map[string]bool)
	var unique []map[string]any
	for _, article := range allArticles {
		title, _ := article["title"].(string)
		key := strings.ToLower(title)
		if len(key) > 40 {
			key = key[:40]
		}
		if !seen[key] {
			seen[key] = true
			unique = append(unique, article)
		}
	}

	slog.Info("news result", "articles", len(unique), "critical", alertCount)

	now := time.Now()
	result := model.NewsData{
		Articles:   unique,
		TotalCount: len(unique),
		AlertCount: alertCount,
		Timestamp:  now.Format(time.RFC3339),
	}

	rawMap := map[string]any{
		"articles":    unique,
		"total_count": len(unique),
		"alert_count": alertCount,
		"timestamp":   now.Format(time.RFC3339),
	}

	return result, rawMap, nil
}

type newsItem struct {
	title string
	desc  string
}

func parseRSS(data []byte) []newsItem {
	var feed rssRoot
	if err := xml.Unmarshal(data, &feed); err != nil {
		return nil
	}
	var items []newsItem
	for _, item := range feed.Channel.Items {
		items = append(items, newsItem{title: item.Title, desc: item.Description})
	}
	return items
}

func parseAtom(data []byte) []newsItem {
	var feed atomFeed
	if err := xml.Unmarshal(data, &feed); err != nil {
		return nil
	}
	var items []newsItem
	for _, entry := range feed.Entries {
		items = append(items, newsItem{title: entry.Title, desc: entry.Summary})
	}
	return items
}
