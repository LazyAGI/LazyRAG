package wordgroup

import (
	"context"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/log"
)

const (
	vocabExtractPath             = "/api/vocab/extract"
	vocabExtractScheduleInterval = 7 * 24 * time.Hour
	vocabExtractHTTPTimeout      = 10 * time.Minute
)

func runVocabExtractOnce(ctx context.Context) {
	url := common.JoinURL(wordGroupServiceURL(), vocabExtractPath)
	body := map[string]any{}
	if err := common.ApiPost(ctx, url, body, nil, nil, vocabExtractHTTPTimeout); err != nil {
		log.Logger.Warn().Err(err).Str("url", url).Msg("vocab extract failed")
		return
	}
	log.Logger.Info().Str("url", url).Msg("vocab extract ok")
}

// StartPeriodicVocabExtract POSTs /api/vocab/extract on the chat service (same base as wordGroupServiceURL):
// once at startup, then every 7 days. Request body is an empty JSON object.
func StartPeriodicVocabExtract(ctx context.Context) {
	log.Logger.Info().Dur("interval", vocabExtractScheduleInterval).Msg("vocab extract schedule started (first run now, then every interval)")
	runVocabExtractOnce(ctx)

	t := time.NewTicker(vocabExtractScheduleInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			runVocabExtractOnce(ctx)
		}
	}
}
