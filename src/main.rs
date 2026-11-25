use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command as ProcessCommand;
use x_social_draft_workflow::{
    DraftSetInput, PromptPolicy, add_post, append_prompt_rule, audit_completeness,
    audit_report_markdown, confirm_account, confirm_liked, confirm_posted, connect_database,
    designate_browser, duplicate_status, load_prompt_policy, prompt_state, record_imported_reply,
    report_markdown, save_drafts, set_prompt, status_summary, stored_prompt,
};

#[derive(Debug, Parser)]
#[command(
    name = "x-social-draft-workflow",
    version,
    about = "Local X post/draft database, duplicate checker, report generator, and isolated headless multi-browser connector."
)]
struct Cli {
    #[arg(
        long,
        global = true,
        default_value = "history.sqlite3",
        help = "SQLite database path"
    )]
    db: PathBuf,
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Initialize the schema without resetting existing records.
    Init,
    /// Show account, browser gate, DB integrity, and record counts.
    Status,
    /// Record the account after confirmation or auto-detection.
    ConfirmAccount {
        #[arg(long)]
        handle: String,
        #[arg(long)]
        display_name: String,
    },
    /// Mark a user-designated, separate browser as ready for background-only work.
    DesignateBrowser {
        #[arg(long)]
        label: String,
    },
    /// List installed browsers (Firefox, Brave, Chrome, Edge), profiles, and active debug ports.
    ListBrowsers,
    /// Connect to any chosen browser (Firefox/Brave/Chrome/Edge), create isolated shortcut/launcher, and auto-detect X user.
    ConnectBrowser {
        #[arg(long, default_value = "auto")]
        browser: String,
        #[arg(long)]
        profile: Option<String>,
        #[arg(long)]
        exe_path: Option<String>,
        #[arg(long)]
        engine: Option<String>,
        #[arg(long)]
        user_data_dir: Option<String>,
        #[arg(long)]
        port: Option<u16>,
        #[arg(long)]
        no_shortcut: bool,
        #[arg(long)]
        no_detect: bool,
    },
    /// Create or refresh Desktop shortcut/launcher (.lnk / .desktop / .command) for the connected isolated browser profile.
    CreateShortcut,
    /// Auto-detect logged-in X handle and display name in isolated headless mode and save to DB.
    AutoDetectAccount {
        #[arg(long)]
        port: Option<u16>,
        #[arg(long)]
        no_confirm: bool,
    },
    /// Save text read from the designated browser; this command does not fetch it directly.
    AddPost {
        #[arg(long)]
        url: String,
        #[arg(long)]
        text_file: PathBuf,
        #[arg(long, default_value = "und")]
        language: String,
    },
    /// Save three assistant-generated English non-question drafts from JSON and run DB duplicate checks.
    SaveDrafts {
        #[arg(long)]
        post_id: i64,
        #[arg(long)]
        file: PathBuf,
    },
    /// Check a candidate reply against recorded posted/imported replies.
    CheckDuplicate {
        #[arg(long)]
        text_file: PathBuf,
    },
    /// Import one historical reply supplied by the user for duplicate checking.
    ImportReply {
        #[arg(long)]
        text_file: PathBuf,
    },
    /// Record that a stored draft was posted.
    ConfirmPosted {
        #[arg(long)]
        draft_id: i64,
    },
    /// Record that a stored post was liked.
    ConfirmLiked {
        #[arg(long)]
        post_id: i64,
    },
    /// Print a Markdown results table.
    Report,
    /// Print the active reply-generation prompt (custom or repo default).
    ShowPrompt {
        #[arg(long)]
        json: bool,
    },
    /// Configure repo default prompt, custom user prompt, or append a logic clarification rule.
    SetPrompt {
        #[arg(long)]
        default: bool,
        #[arg(long)]
        file: Option<PathBuf>,
        #[arg(long)]
        text: Option<String>,
        #[arg(long)]
        append_rule: Option<String>,
        #[arg(long)]
        language: Option<String>,
        #[arg(long)]
        min_words: Option<usize>,
        #[arg(long)]
        max_words: Option<usize>,
        #[arg(long)]
        allow_questions: bool,
        #[arg(long)]
        no_project_short: bool,
        #[arg(long)]
        allow_symbols: bool,
        #[arg(long)]
        json: bool,
    },
    /// Run strict completeness audit against expected URLs or plan JSON and print a Markdown table.
    Audit {
        #[arg(long)]
        urls_file: Option<PathBuf>,
        #[arg(long)]
        plan: Option<PathBuf>,
        #[arg(long)]
        json: bool,
        #[arg(long)]
        strict: bool,
    },
}

fn read_text(path: &PathBuf) -> Result<String> {
    fs::read_to_string(path).with_context(|| format!("reading UTF-8 text file {}", path.display()))
}

fn find_browser_hub_script() -> Result<PathBuf> {
    let rel = Path::new(".agents/skills/x-social-browser-workflow/scripts/browser_hub.py");
    if rel.exists() {
        return Ok(rel.to_path_buf());
    }
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent().map(Path::to_path_buf);
        for _ in 0..4 {
            if let Some(d) = dir {
                let candidate = d.join(rel);
                if candidate.exists() {
                    return Ok(candidate);
                }
                dir = d.parent().map(Path::to_path_buf);
            }
        }
    }
    bail!(
        "browser_hub.py not found at .agents/skills/x-social-browser-workflow/scripts/browser_hub.py"
    );
}

fn resolve_python_bin(script_path: &Path) -> String {
    let mut local_candidates: Vec<PathBuf> = Vec::new();
    for root in script_path.ancestors().take(7) {
        if root.as_os_str().is_empty() {
            continue;
        }
        if cfg!(windows) {
            local_candidates.push(root.join(".venv").join("Scripts").join("python.exe"));
        } else {
            local_candidates.push(root.join(".venv").join("bin").join("python3"));
            local_candidates.push(root.join(".venv").join("bin").join("python"));
        }
    }
    if cfg!(windows) {
        local_candidates.push(PathBuf::from(".venv/Scripts/python.exe"));
    } else {
        local_candidates.push(PathBuf::from(".venv/bin/python3"));
        local_candidates.push(PathBuf::from(".venv/bin/python"));
    }
    for cand in local_candidates {
        if cand.exists() {
            return cand.to_string_lossy().into_owned();
        }
    }

    let names: &[&str] = if cfg!(windows) {
        &["python", "python3"]
    } else {
        &["python3", "python"]
    };
    for name in names {
        if let Ok(status) = ProcessCommand::new(name)
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            && status.success()
        {
            return (*name).to_owned();
        }
    }
    if cfg!(windows) {
        "python".to_owned()
    } else {
        "python3".to_owned()
    }
}

fn run_browser_hub(db: &Path, sub_args: &[String]) -> Result<()> {
    let script = find_browser_hub_script()?;
    let python_bin = resolve_python_bin(&script);
    let mut cmd = ProcessCommand::new(&python_bin);
    cmd.arg(&script)
        .arg("--db")
        .arg(db);
    if let Ok(exe) = std::env::current_exe() {
        cmd.arg("--cli-path").arg(exe);
    }
    cmd.args(sub_args);
    let status = cmd
        .status()
        .with_context(|| format!("running {python_bin} {}", script.display()))?;
    if !status.success() {
        bail!("browser_hub.py exited with status {status}");
    }
    Ok(())
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let connection = connect_database(&cli.db)?;

    match cli.command {
        Command::Init => {
            println!(
                "Database initialized without resetting existing rows: {}",
                cli.db.display()
            );
        }
        Command::Status => {
            let status = status_summary(&connection)?;
            println!("{}", serde_json::to_string_pretty(&status)?);
            if status.integrity != "ok" {
                bail!("database integrity check did not return ok");
            }
        }
        Command::ConfirmAccount {
            handle,
            display_name,
        } => {
            confirm_account(&connection, &handle, &display_name)?;
            println!("Confirmed account recorded: {handle}.");
        }
        Command::DesignateBrowser { label } => {
            designate_browser(&connection, &label)?;
            println!("Separate browser recorded as designated: {label}.");
        }
        Command::ListBrowsers => {
            drop(connection);
            run_browser_hub(&cli.db, &["list-browsers".to_string()])?;
        }
        Command::ConnectBrowser {
            browser,
            profile,
            exe_path,
            engine,
            user_data_dir,
            port,
            no_shortcut,
            no_detect,
        } => {
            drop(connection);
            let mut args = vec![
                "connect".to_string(),
                "--browser".to_string(),
                browser,
            ];
            if let Some(p) = profile {
                args.extend(["--profile".to_string(), p]);
            }
            if let Some(e) = exe_path {
                args.extend(["--exe-path".to_string(), e]);
            }
            if let Some(eng) = engine {
                args.extend(["--engine".to_string(), eng]);
            }
            if let Some(ud) = user_data_dir {
                args.extend(["--user-data-dir".to_string(), ud]);
            }
            if let Some(pt) = port {
                args.extend(["--port".to_string(), pt.to_string()]);
            }
            if no_shortcut {
                args.push("--no-shortcut".to_string());
            }
            if no_detect {
                args.push("--no-detect".to_string());
            }
            run_browser_hub(&cli.db, &args)?;
        }
        Command::CreateShortcut => {
            drop(connection);
            run_browser_hub(&cli.db, &["create-shortcut".to_string()])?;
        }
        Command::AutoDetectAccount { port, no_confirm } => {
            drop(connection);
            let mut args = vec!["detect-account".to_string()];
            if let Some(pt) = port {
                args.extend(["--port".to_string(), pt.to_string()]);
            }
            if no_confirm {
                args.push("--no-confirm".to_string());
            }
            run_browser_hub(&cli.db, &args)?;
        }
        Command::AddPost {
            url,
            text_file,
            language,
        } => {
            let text = read_text(&text_file)?;
            let id = add_post(&connection, &url, &text, &language)?;
            println!("Saved visible post text as database row {id}.");
        }
        Command::SaveDrafts { post_id, file } => {
            let json = read_text(&file)?;
            let drafts: DraftSetInput = serde_json::from_str(&json)
                .with_context(|| format!("parsing draft JSON {}", file.display()))?;
            let result = save_drafts(&connection, post_id, &drafts)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Command::CheckDuplicate { text_file } => {
            let text = read_text(&text_file)?;
            let account = status_summary(&connection)?
                .account_handle
                .ok_or_else(|| anyhow::anyhow!("no active account is recorded"))?;
            let duplicate = duplicate_status(&connection, &account, &text)?;
            println!(
                "{{\"account\":{},\"duplicate_in_recorded_history\":{}}}",
                serde_json::to_string(&account)?,
                duplicate
            );
        }
        Command::ImportReply { text_file } => {
            let text = read_text(&text_file)?;
            let account = status_summary(&connection)?
                .account_handle
                .ok_or_else(|| anyhow::anyhow!("no active account is recorded"))?;
            record_imported_reply(&connection, &account, &text)?;
            println!(
                "Imported historical reply for {account}; duplicate checking now includes it."
            );
        }
        Command::ConfirmPosted { draft_id } => {
            confirm_posted(&connection, draft_id)?;
            println!("Recorded posting confirmation for draft {draft_id}.");
        }
        Command::ConfirmLiked { post_id } => {
            confirm_liked(&connection, post_id)?;
            println!("Recorded Like confirmation for post {post_id}.");
        }
        Command::Report => print!("{}", report_markdown(&connection)?),
        Command::ShowPrompt { json } => {
            if json {
                let state = prompt_state(&connection)?;
                println!("{}", serde_json::to_string_pretty(&state)?);
            } else {
                print!("{}", stored_prompt(&connection)?);
            }
        }
        Command::SetPrompt {
            default,
            file,
            text,
            append_rule,
            language,
            min_words,
            max_words,
            allow_questions,
            no_project_short,
            allow_symbols,
            json,
        } => {
            if let Some(rule) = append_rule {
                let state = append_prompt_rule(&connection, &rule)?;
                if json {
                    println!("{}", serde_json::to_string_pretty(&state)?);
                } else {
                    println!(
                        "Logic clarification rule appended (source={}).",
                        state.source
                    );
                }
            } else {
                let has_policy_override = language.is_some()
                    || min_words.is_some()
                    || max_words.is_some()
                    || allow_questions
                    || no_project_short
                    || allow_symbols;
                let policy_override = if has_policy_override {
                    let mut pol = if default {
                        PromptPolicy::default()
                    } else {
                        load_prompt_policy(&connection)?
                    };
                    if let Some(lang) = language {
                        pol.language = lang;
                    }
                    if let Some(min_w) = min_words {
                        pol.min_words = min_w;
                    }
                    if let Some(max_w) = max_words {
                        pol.max_words = max_w;
                    }
                    if allow_questions {
                        pol.allow_questions = true;
                    }
                    if no_project_short {
                        pol.require_project_short = false;
                    }
                    if allow_symbols {
                        pol.allow_forbidden_symbols = true;
                    }
                    Some(pol)
                } else {
                    None
                };

                let custom_text = if let Some(path) = file {
                    Some(read_text(&path)?)
                } else {
                    text
                };
                let state = set_prompt(
                    &connection,
                    default,
                    custom_text.as_deref(),
                    policy_override.as_ref(),
                )?;
                if json {
                    println!("{}", serde_json::to_string_pretty(&state)?);
                } else {
                    println!(
                        "Active prompt configured (source={}, language={}, words={}..={}, require_project_short={}, allow_questions={}).",
                        state.source,
                        state.policy.language,
                        state.policy.min_words,
                        state.policy.max_words,
                        state.policy.require_project_short,
                        state.policy.allow_questions
                    );
                }
            }
        }
        Command::Audit {
            urls_file,
            plan,
            json,
            strict,
        } => {
            let mut expected_urls: Vec<String> = Vec::new();
            if let Some(uf) = urls_file {
                let raw = read_text(&uf)?;
                for line in raw.lines() {
                    let s = line.trim();
                    if !s.is_empty() && !s.starts_with('#') {
                        expected_urls.push(s.to_owned());
                    }
                }
            }
            if let Some(pf) = plan {
                let raw = read_text(&pf)?;
                let parsed: serde_json::Value = serde_json::from_str(&raw)
                    .with_context(|| format!("parsing plan JSON {}", pf.display()))?;
                if let Some(arr) = parsed.as_array() {
                    for entry in arr {
                        if let Some(u) = entry.get("url").and_then(|v| v.as_str()) {
                            expected_urls.push(u.to_owned());
                        }
                    }
                }
            }
            let audit = audit_completeness(&connection, &expected_urls)?;
            if json {
                println!("{}", serde_json::to_string_pretty(&audit)?);
            } else {
                print!("{}", audit_report_markdown(&audit));
            }
            if strict && !audit.all_complete {
                bail!(
                    "strict audit failed: {}/{} complete ({} incomplete/missing)",
                    audit.complete_count,
                    audit.total_expected,
                    audit.incomplete_count
                );
            }
        }
    }
    Ok(())
}
