package worker

import (
	"testing"
	"time"
)

func TestRetryBackoff(t *testing.T) {
	t.Parallel()
	base := 2 * time.Second
	max := 30 * time.Second
	cases := []struct {
		retry int
		want  time.Duration
	}{
		{retry: 1, want: 2 * time.Second},
		{retry: 2, want: 4 * time.Second},
		{retry: 3, want: 8 * time.Second},
		{retry: 4, want: 16 * time.Second},
		{retry: 5, want: 30 * time.Second},
		{retry: 10, want: 30 * time.Second},
	}
	for _, tc := range cases {
		if got := retryBackoff(base, max, tc.retry); got != tc.want {
			t.Fatalf("retry=%d: expected %v, got %v", tc.retry, tc.want, got)
		}
	}
}
