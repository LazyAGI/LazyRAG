// Package log provides a console logger (zerolog).
package log

import (
	"os"
	"time"

	"github.com/rs/zerolog"
)

// Logger text zerolog.Logger，text main text dbmigrate text Init() text
var Logger zerolog.Logger

// Init Initializetext Logger：text stdout，text，text。text docker logs text
func Init() {
	Logger = zerolog.New(zerolog.ConsoleWriter{
		Out:        os.Stdout,
		TimeFormat: time.RFC3339,
	}).With().Timestamp().Logger()
}

// InitNop text Logger text Nop，text Init textLog
func InitNop() {
	Logger = zerolog.Nop()
}
