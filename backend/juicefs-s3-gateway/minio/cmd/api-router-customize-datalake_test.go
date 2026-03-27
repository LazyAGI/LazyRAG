package cmd

import (
	"testing"
)

func Test_Path(t *testing.T) {
	if valid := isValidPath("/rag/job/123/hello.pdf", validPurposeMap, false); !valid {
		t.Error("invalid name")
		return
	}

	purpose, filename, valid := getFileMeta("/rag/job/123/hello.pdf")
	if purpose != "rag" || filename != "hello.pdf" || !valid {
		t.Errorf("invalid name, %s, %s, %v", purpose, filename, valid)
		return
	}

	id, obj, err := calculateFilePath("/rag/job/123/hello.pdf")
	if err != nil {
		t.Errorf("calculateFilePath err, err: %v", err)
		return
	}

	object, err := getFileObjectName(id, userInfo{UserID: "jintong"})
	if err != nil {
		t.Errorf("getFileObjectName failed, err: %v", err)
		return
	}
	if obj != object {
		t.Errorf("invalid calculate")
	}

	purpose_, _ := extractFileMetas("/jintong/rag/job/123/hello.pdf", userInfo{UserID: "jintong"})
	if purpose != purpose_ {
		t.Errorf("invalid purpose, want: %s, have: %s", purpose, purpose_)
	}
}

func Test_Filename(t *testing.T) {
	purpose, filename := extractFileMetas("/jintong/finetune/test/hello.pdf", userInfo{UserID: "jintong"})
	t.Logf("%s %s", purpose, filename)
}

func Test_Generate(t *testing.T) {
	purpose, filename, err := generateObjectName("/rag/hello_word/star_output.pdf", "rag", userInfo{UserID: "jintong"})
	t.Logf("%s %s %v", purpose, filename, err)
}

func Test_TransID(t *testing.T) {
	id := "ISekQsSeLlzUHjT6iEBbYWGvI6qYBupFrHSv2S7CgQ8"
	object, _ := getFileObjectName(id, userInfo{UserID: "jintong"})
	t.Logf("%s", object)
}

func Test_SpecialPathID(t *testing.T) {
	//path := "/rag/owxtest/兰新线精河至阿拉山口增建二线可研-分篇-牵引供电与电力.docx"
	//path := "/rag/owxtest/hello.docx"
	path := "/chat/1757036461074/10kV513三星口线013支_#005_耐张杆(不含开关)_大号侧电气连接_T.JPG"
	purpose := "chat"
	user := userInfo{
		UserID:   "7682a7a5-4065-5147-ac5f-2b188772f8b0",
		UserName: "6737c177-2d00-5792-949e-ffeca6e9860c",
	}
	a, b, c := generateObjectName(path, purpose, user)
	t.Logf("%v\n%v\n%v\n", a, b, c)
}

func Test_IDTrans(t *testing.T) {
	id := "HuM61sifWqfpUGc0reu9HTMmAvRRW7AUmYehQ95zSzTuEv7fDm1597CE62lCNi7FMJgSQ5pfCOMtaubLZgquQeYypCH567fNKoyi9jt5h9nD4OqwUceXop5jWWAJPoPBgWUJake5l89ZtzSMh1vtAq5VoLzcUv4C9OBW94bCFfEMNsdZyb5lVWXVzfmbTiAydb5fSLgywVxQhofCO6LYBO4"
	user := userInfo{
		UserID:   "6737c177-2d00-5792-949e-ffeca6e9860c",
		UserName: "7682a7a5-4065-5147-ac5f-2b188772f8b0",
	}
	object, err := getFileObjectName(id, user)
	if err != nil {
		t.Error(err)
	}
	t.Logf(object)
}
