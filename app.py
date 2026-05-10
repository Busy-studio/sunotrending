def render_top_table(df):
    css = """
    <style>
    html, body {
        margin: 0;
        padding: 0;
        font-family:
            "Noto Sans KR",
            "Noto Sans",
            "Apple SD Gothic Neo",
            "Malgun Gothic",
            "Segoe UI",
            "Segoe UI Symbol",
            "Apple Color Emoji",
            "Noto Color Emoji",
            Arial,
            sans-serif;
        background: #ffffff;
        color: #111827;
    }

    .table-wrap {
        width: 100%;
        overflow-x: auto;
        background: #ffffff;
    }

    table.song-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        table-layout: fixed;
        color: #111827;
    }

    .song-table th {
        text-align: left;
        padding: 11px 8px;
        border-bottom: 1px solid #d1d5db;
        background: #f3f4f6;
        position: sticky;
        top: 0;
        z-index: 2;
        font-weight: 800;
        color: #111827;
    }

    .song-table td {
        padding: 8px;
        border-bottom: 1px solid #e5e7eb;
        vertical-align: middle;
        color: #111827;
    }

    .song-table tr:hover {
        background: #f9fafb;
    }

    .rank {
        font-weight: 800;
        font-size: 16px;
        text-align: right;
        width: 44px;
        color: #111827;
    }

    .cover-btn {
        border: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        cursor: pointer;
        position: relative;
        width: 56px;
        height: 56px;
        display: block;
    }

    .cover {
        width: 56px;
        height: 56px;
        object-fit: cover;
        border-radius: 10px;
        background: #e5e7eb;
        display: block;
    }

    .cover-btn::after {
        content: "▶";
        position: absolute;
        right: 4px;
        bottom: 4px;
        width: 20px;
        height: 20px;
        border-radius: 999px;
        background: rgba(0,0,0,0.72);
        color: white;
        font-size: 11px;
        line-height: 20px;
        text-align: center;
        font-weight: 800;
    }

    .cover-btn.playing::after {
        content: "Ⅱ";
        background: rgba(239,68,68,0.88);
    }

    .empty-cover {
        width: 56px;
        height: 56px;
        border-radius: 10px;
        background: #e5e7eb;
    }

    .title-cell {
        overflow: hidden;
        word-break: break-word;
        color: #111827;
    }

    .title-link {
        font-weight: 800;
        text-decoration: none;
        color: #111827;
        display: inline-block;
        max-width: 100%;
        white-space: normal;
        line-height: 1.35;
    }

    .title-link:hover {
        text-decoration: underline;
        color: #ef4444;
    }

    .subtle {
        color: #6b7280;
        font-size: 12px;
        margin-top: 4px;
        line-height: 1.25;
    }

    .creator {
        line-height: 1.35;
        word-break: break-word;
        color: #111827;
    }

    .num {
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
        color: #111827;
    }

    .score {
        font-weight: 800;
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
        color: #111827;
    }
    </style>
    """

    js = """
    <script>
    let currentAudio = null;
    let currentButton = null;

    function toggleAudio(button) {
        const url = button.getAttribute("data-audio");

        if (!url || url === "nan" || url === "None") {
            alert("이 곡에는 audio_url이 없습니다.");
            return;
        }

        if (currentAudio && currentButton === button) {
            if (currentAudio.paused) {
                currentAudio.play();
                button.classList.add("playing");
            } else {
                currentAudio.pause();
                button.classList.remove("playing");
            }
            return;
        }

        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
        }

        if (currentButton) {
            currentButton.classList.remove("playing");
        }

        currentAudio = new Audio(url);
        currentButton = button;

        currentAudio.addEventListener("ended", function() {
            button.classList.remove("playing");
        });

        currentAudio.play()
            .then(function() {
                button.classList.add("playing");
            })
            .catch(function(err) {
                console.log(err);
                alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
            });
    }
    </script>
    """

    rows = []

    for _, r in df.iterrows():
        image = safe_url(r.get("image_url", ""))
        audio_url = safe_url(r.get("audio_url", ""))
        song_url = safe_url(r.get("song_url", ""))
        title = esc(r.get("title", "Untitled"))
        handle = esc(r.get("handle", ""))
        display_name = esc(r.get("display_name", ""))

        creator = display_name or handle
        if handle and display_name and handle.lower() not in display_name.lower():
            creator = f"{display_name}<div class='subtle'>@{handle}</div>"
        elif handle:
            creator = f"@{handle}"

        created_at = r.get("created_at")
        if pd.notna(created_at):
            created_txt = created_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            created_txt = "-"

        if image:
            img_html = (
                f"<button class='cover-btn' data-audio='{html.escape(audio_url)}' "
                f"onclick='toggleAudio(this)' title='재생 / 일시정지'>"
                f"<img class='cover' src='{html.escape(image)}' loading='lazy'>"
                f"</button>"
            )
        else:
            img_html = (
                f"<button class='cover-btn' data-audio='{html.escape(audio_url)}' "
                f"onclick='toggleAudio(this)' title='재생 / 일시정지'>"
                f"<div class='empty-cover'></div>"
                f"</button>"
            )

        if song_url:
            title_html = (
                f"<a class='title-link' href='{html.escape(song_url)}' "
                f"target='_blank' rel='noopener noreferrer'>{title}</a>"
            )
        else:
            title_html = title

        rows.append(
            f"""
            <tr>
                <td class="rank">{int(r.get("rank", 0))}</td>
                <td>{img_html}</td>
                <td class="title-cell">
                    {title_html}
                    <div class="subtle">{created_txt}</div>
                </td>
                <td class="creator">{creator}</td>
                <td class="num">{fmt_int(r.get("play_count", 0))}</td>
                <td class="num">{fmt_int(r.get("upvote_count", 0))}</td>
                <td class="num">{fmt_int(r.get("comment_count", 0))}</td>
                <td class="score">{fmt_float(r.get("trend_score", 0), 1)}</td>
            </tr>
            """
        )

    table_html = f"""
    {css}
    {js}
    <div class="table-wrap">
        <table class="song-table">
            <thead>
                <tr>
                    <th style="width:44px; text-align:right;">순위</th>
                    <th style="width:72px;">앨범</th>
                    <th>곡 제목</th>
                    <th style="width:190px;">원작자</th>
                    <th style="width:90px; text-align:right;">플레이</th>
                    <th style="width:90px; text-align:right;">좋아요</th>
                    <th style="width:80px; text-align:right;">댓글</th>
                    <th style="width:90px; text-align:right;">점수</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """

    height = min(12000, max(600, 92 + len(df) * 74))

    components.html(
        table_html,
        height=height,
        scrolling=True,
    )
