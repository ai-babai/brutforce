import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookmarkSimple,
  Camera,
  Check,
  House,
  ImageSquare,
  MagnifyingGlass,
  Pause,
  Play,
  X,
} from "@phosphor-icons/react";
import { IconDroplet, IconGlassFull, IconMapPin } from "@tabler/icons-react";
import {
  getCatalog,
  getRecommendations,
  InvalidPhotoError,
  StaleCatalogCursorError,
  savePhotoFeedback,
  searchWine,
  uploadPhoto,
} from "./api";
import type { Candidate, FeedbackDecision, FeedbackReceipt, PhotoReceipt, Scenario } from "./types";
import { AtlasScan } from "./AtlasIcons";
import { InstallApp } from "./InstallApp";
import { MascotScene, V2Logo } from "./V2Visual";
import { shuffleWineNotes, wineNotes } from "./wineNotes";

type Screen =
  | "welcome"
  | "camera"
  | "permission"
  | "settings"
  | "loading"
  | "waiting"
  | "result"
  | "candidates"
  | "search"
  | "saved"
  | "missing"
  | "badphoto"
  | "error";
type CandidateOrigin = "scan" | "manual" | "correction";
type ResultOrigin = CandidateOrigin | "catalog" | "saved";
type SearchOrigin = "normal" | "correction";
type ErrorKind = "network" | "server";
type MissingReason = "no_match" | "outside_display" | "rejected";
type RecommendationStatus = "idle" | "loading" | "ready" | "empty" | "error";
const savedKey = "wine-demo-saved-v1";

export function App({
  initialScenario = "exact",
  simulatePermissionDenied = false,
}: { initialScenario?: Scenario; simulatePermissionDenied?: boolean } = {}) {
  const [screen, setScreen] = useState<Screen>("welcome");
  const [section, setSection] = useState<"scanner" | "search" | "saved">(
    "scanner",
  );
  const [scenario] = useState<Scenario>(initialScenario);
  const [photo, setPhoto] = useState<string>();
  const [photoFile, setPhotoFile] = useState<File>();
  const [receipt, setReceipt] = useState<PhotoReceipt>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [catalog, setCatalog] = useState<Candidate[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogFailedAppend, setCatalogFailedAppend] = useState(false);
  const [catalogStaleCursor, setCatalogStaleCursor] = useState(false);
  const [catalogNextCursor, setCatalogNextCursor] = useState<string>();
  const [catalogVersion, setCatalogVersion] = useState("");
  const [catalogDemo, setCatalogDemo] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogDebouncing, setCatalogDebouncing] = useState(false);
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogDisplayedQuery, setCatalogDisplayedQuery] = useState("");
  const [catalogInitialized, setCatalogInitialized] = useState(false);
  const [saved, setSaved] = useState<Candidate[]>([]);
  const [storageNotice, setStorageNotice] = useState("");
  const [selected, setSelected] = useState<Candidate>();
  const [query, setQuery] = useState("");
  const [permissionDenied] = useState(simulatePermissionDenied);
  const [expandedPhoto, setExpandedPhoto] = useState(false);
  const [candidateOrigin, setCandidateOrigin] =
    useState<CandidateOrigin>("scan");
  const [resultOrigin, setResultOrigin] = useState<ResultOrigin>("scan");
  const [candidateHasPhoto, setCandidateHasPhoto] = useState(false);
  const [resultHasPhoto, setResultHasPhoto] = useState(false);
  const [resultFromCorrection, setResultFromCorrection] = useState(false);
  const [searchOrigin, setSearchOrigin] = useState<SearchOrigin>("normal");
  const [errorKind, setErrorKind] = useState<ErrorKind>("server");
  const [missingReason, setMissingReason] = useState<MissingReason>("no_match");
  const [notePaused, setNotePaused] = useState(false);
  const [noteIndex, setNoteIndex] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [tabHidden, setTabHidden] = useState(document.hidden);
  const [noteSearchId, setNoteSearchId] = useState(0);
  const noteDeck = useRef<number[]>([]);
  const noteCursor = useRef(0);
  const [recommendations, setRecommendations] = useState<{
    status: RecommendationStatus;
    candidates: Candidate[];
  }>({ status: "idle", candidates: [] });
  const [recommendationAttempt, setRecommendationAttempt] = useState(0);
  const [demoMode, setDemoMode] = useState(false);
  const [feedbackToken, setFeedbackToken] = useState("");
  const [feedbackMode, setFeedbackMode] = useState<"idle" | "correcting" | "saving" | "saved" | "error">("idle");
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState<Candidate>();
  const [feedbackReceipt, setFeedbackReceipt] = useState<FeedbackReceipt>();
  const [feedbackError, setFeedbackError] = useState("");
  const [feedbackQuery, setFeedbackQuery] = useState("");
  const [feedbackCatalog, setFeedbackCatalog] = useState<Candidate[]>([]);
  const [feedbackCatalogCursor, setFeedbackCatalogCursor] = useState<string>();
  const [feedbackCatalogLoading, setFeedbackCatalogLoading] = useState(false);
  const [feedbackCatalogError, setFeedbackCatalogError] = useState("");
  const abort = useRef<AbortController | undefined>(undefined);
  const catalogAbort = useRef<AbortController | undefined>(undefined);
  const catalogTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const catalogGeneration = useRef(0);
  const catalogComposing = useRef(false);
  const recommendationAbort = useRef<AbortController | undefined>(undefined);
  const waitTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const lastRequest = useRef<{
    scenario: Scenario;
    query?: string;
    hasPhoto: boolean;
  }>({ scenario: "exact", hasPhoto: false });
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const queryRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const contentRef = useRef<HTMLDivElement>(null);
  const previousScreen = useRef<Screen>("welcome");
  const cameraReturn = useRef<Screen>("welcome");
  const searchScroll = useRef(0);
  const listScroll = useRef(0);
  const candidateResultHistory = useRef(false);
  const feedbackIdempotency = useRef("");
  const feedbackGeneration = useRef(0);
  const feedbackCatalogAbort = useRef<AbortController | undefined>(undefined);
  const [catalogOpen, setCatalogOpen] = useState(false);

  const resetFeedback = () => {
    feedbackGeneration.current += 1;
    feedbackCatalogAbort.current?.abort();
    setFeedbackToken("");
    setFeedbackMode("idle");
    setFeedbackComment("");
    setFeedbackTarget(undefined);
    setFeedbackReceipt(undefined);
    setFeedbackError("");
    setFeedbackQuery("");
    setFeedbackCatalog([]);
    setFeedbackCatalogCursor(undefined);
    setFeedbackCatalogLoading(false);
    setFeedbackCatalogError("");
    feedbackIdempotency.current = "";
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = undefined;
  };
  const discardCandidateResultHistory = () => {
    if (!candidateResultHistory.current) return;
    candidateResultHistory.current = false;
    window.history.back();
  };
  const clearWaitTimer = (controller?: AbortController) => {
    if (!controller || abort.current === controller) {
      if (waitTimer.current) clearTimeout(waitTimer.current);
      waitTimer.current = undefined;
    }
  };
  const classifyError = (error: unknown): ErrorKind =>
    error instanceof TypeError ? "network" : "server";
  useEffect(
    () => () => {
      abort.current?.abort();
      catalogAbort.current?.abort();
      if (catalogTimer.current) clearTimeout(catalogTimer.current);
      recommendationAbort.current?.abort();
      feedbackCatalogAbort.current?.abort();
      stopCamera();
      if (waitTimer.current) clearTimeout(waitTimer.current);
    },
    [],
  );
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return;
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  useEffect(() => {
    const update = () => setTabHidden(document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const notesActive = ["loading", "waiting"].includes(screen) && !notePaused && !reducedMotion && !tabHidden && !expandedPhoto;
  useEffect(() => {
    if (!notesActive) return;
    const timer = window.setTimeout(() => {
      if (noteCursor.current + 1 === wineNotes.length) {
        noteDeck.current = shuffleWineNotes(Math.random, noteDeck.current[noteCursor.current]);
        noteCursor.current = 0;
      } else noteCursor.current += 1;
      setNoteIndex(noteDeck.current[noteCursor.current]);
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [notesActive, noteIndex, noteSearchId]);
  const beginWineNotes = () => {
    const previous = noteDeck.current[noteCursor.current];
    noteDeck.current = shuffleWineNotes(Math.random, previous);
    noteCursor.current = 0;
    setNoteIndex(noteDeck.current[0]);
    setNoteSearchId((id) => id + 1);
  };
  useEffect(
    () => () => {
      if (photo?.startsWith("blob:")) URL.revokeObjectURL(photo);
    },
    [photo],
  );
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    if (screen === "search" && previousScreen.current === "result" && resultOrigin === "catalog")
      content.scrollTop = listScroll.current;
    else if (screen === "saved" && previousScreen.current === "result" && resultOrigin === "saved")
      content.scrollTop = listScroll.current;
    else if (screen === "candidates" && previousScreen.current === "result")
      content.scrollTop = listScroll.current;
    else if (screen === "search")
      content.scrollTop =
        previousScreen.current === "candidates" ? searchScroll.current : 0;
    else content.scrollTop = 0;
    previousScreen.current = screen;
  }, [screen, selected?.id]);
  useEffect(() => {
    if (screen !== "result" || !selected) {
      recommendationAbort.current?.abort();
      setRecommendations({ status: "idle", candidates: [] });
      return;
    }
    const controller = new AbortController();
    recommendationAbort.current?.abort();
    recommendationAbort.current = controller;
    setRecommendations({ status: "loading", candidates: [] });
    getRecommendations(selected.id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted || recommendationAbort.current !== controller)
          return;
        setRecommendations({
          status: data.candidates.length ? "ready" : "empty",
          candidates: data.candidates,
        });
      })
      .catch(() => {
        if (!controller.signal.aborted && recommendationAbort.current === controller)
          setRecommendations({ status: "error", candidates: [] });
      });
    return () => controller.abort();
  }, [screen, selected?.id, recommendationAttempt]);
  useEffect(() => {
    if (screen !== "camera" || permissionDenied) return;
    let active = true;
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error();
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
      } catch {
        if (active) setScreen("permission");
      }
    })();
    return () => {
      active = false;
      stopCamera();
    };
  }, [screen, permissionDenied]);
  const validPhoto = (file: File) =>
    ["image/jpeg", "image/png", "image/gif"].includes(file.type) &&
    file.size <= 10 * 1024 * 1024;
  const pickPhoto = (file?: File) => {
    if (!file) return;
    if (!validPhoto(file)) {
      if (screen !== "camera") cameraReturn.current = screen;
      setScreen("badphoto");
      return;
    }
    stopCamera();
    setCandidates([]);
    setSelected(undefined);
    setCandidateHasPhoto(false);
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setMissingReason("no_match");
    setSection("search");
    setPhotoFile(file);
    setReceipt(undefined);
    resetFeedback();
    setPhoto(URL.createObjectURL(file));
    uploadThenSearch(file, scenario);
  };
  const uploadThenSearch = async (file: File, next: Scenario, q?: string) => {
    beginWineNotes();
    abort.current?.abort();
    clearWaitTimer();
    const controller = new AbortController();
    abort.current = controller;
    lastRequest.current = {
      scenario: next,
      hasPhoto: true,
      ...(q ? { query: q } : {}),
    };
    setScreen("loading");
    waitTimer.current = setTimeout(() => {
      if (!controller.signal.aborted && abort.current === controller)
        setScreen("waiting");
    }, 1200);
    try {
      const saved = await uploadPhoto(file, controller.signal);
      if (controller.signal.aborted || abort.current !== controller) return;
      setReceipt(saved);
      await runSearch(next, q, saved, controller);
    } catch (e) {
      if (
        !controller.signal.aborted &&
        abort.current === controller &&
        (e as Error).name !== "AbortError"
      ) {
        clearWaitTimer(controller);
        if (e instanceof InvalidPhotoError) setScreen("badphoto");
        else {
          setErrorKind(classifyError(e));
          setScreen("error");
        }
      }
    }
  };
  const runSearch = async (
    next: Scenario = scenario,
    q?: string,
    knownReceipt?: PhotoReceipt,
    existingController?: AbortController,
  ) => {
    if (!existingController) beginWineNotes();
    if (!existingController) abort.current?.abort();
    clearWaitTimer(existingController);
    const controller = existingController ?? new AbortController();
    abort.current = controller;
    lastRequest.current = {
      scenario: next,
      hasPhoto: Boolean(knownReceipt),
      ...(q ? { query: q } : {}),
    };
    setScreen("loading");
    waitTimer.current = setTimeout(() => {
      if (!controller.signal.aborted && abort.current === controller)
        setScreen("waiting");
    }, 1200);
    try {
      const data = await searchWine(
        next,
        q,
        controller.signal,
        knownReceipt?.id,
      );
      if (controller.signal.aborted || abort.current !== controller) return;
      clearWaitTimer(controller);
      setDemoMode(data.demo);
      setFeedbackToken(data.feedbackToken ?? "");
      setFeedbackMode("idle");
      setFeedbackComment("");
      setFeedbackTarget(undefined);
      setFeedbackReceipt(undefined);
      setFeedbackError("");
      feedbackIdempotency.current = "";
      const list = data.candidates;
      setCandidates(list);
      if (!list.length) {
        setMissingReason(
          data.action === "outside_display_catalog" ? "outside_display" : "no_match",
        );
        setScreen("missing");
        return;
      }
      setCandidateOrigin(q ? searchOrigin === "correction" ? "correction" : "manual" : "scan");
      setCandidateHasPhoto(Boolean(knownReceipt));
      setScreen("candidates");
    } catch (e) {
      if (
        !controller.signal.aborted &&
        abort.current === controller &&
        (e as Error).name !== "AbortError"
      ) {
        clearWaitTimer(controller);
        setErrorKind(classifyError(e));
        setScreen("error");
      }
    }
  };
  const retry = () =>
    lastRequest.current.query
      ? (setQuery(lastRequest.current.query), submitCatalogSearch())
      :
    lastRequest.current.hasPhoto
      ? receipt
        ? runSearch(
            lastRequest.current.scenario,
            lastRequest.current.query,
            receipt,
          )
        : photoFile
          ? uploadThenSearch(
              photoFile,
              lastRequest.current.scenario,
              lastRequest.current.query,
            )
          : setScreen("badphoto")
      : setScreen("badphoto");
  const clearPhotoPath = () => {
    setPhoto(undefined);
    setPhotoFile(undefined);
    setReceipt(undefined);
    setCandidates([]);
    setSelected(undefined);
    setCandidateHasPhoto(false);
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setMissingReason("no_match");
    lastRequest.current = { scenario, hasPhoto: false };
  };
  const cancel = () => {
    discardCandidateResultHistory();
    abort.current?.abort();
    catalogAbort.current?.abort();
    if (catalogTimer.current) clearTimeout(catalogTimer.current);
    setCatalogLoading(false);
    setCatalogDebouncing(false);
    catalogGeneration.current += 1;
    clearWaitTimer();
    setExpandedPhoto(false);
    clearPhotoPath();
    setSection("scanner");
    setScreen("welcome");
  };
  const openCamera = () => {
    cameraReturn.current = screen;
    if (screen === "missing" && missingReason === "rejected") setMissingReason("rejected");
    permissionDenied ? setScreen("permission") : setScreen("camera");
  };
  const backFromCamera = () => {
    stopCamera();
    setScreen(cameraReturn.current);
  };
  const leaveWork = () => {
    discardCandidateResultHistory();
    abort.current?.abort();
    catalogAbort.current?.abort();
    if (catalogTimer.current) clearTimeout(catalogTimer.current);
    setCatalogLoading(false);
    setCatalogDebouncing(false);
    catalogComposing.current = false;
    catalogGeneration.current += 1;
    if (waitTimer.current) clearTimeout(waitTimer.current);
    stopCamera();
    setExpandedPhoto(false);
  };
  const newCapture = () => {
    leaveWork();
    openCamera();
  };
  const openSearch = () => {
    leaveWork();
    setSection("search");
    setSearchOrigin("normal");
    setPhoto(undefined);
    setPhotoFile(undefined);
    setReceipt(undefined);
    setSelected(undefined);
    setCandidates([]);
    if (screen !== "welcome") {
      setQuery("");
      setCatalogQuery("");
      setCatalog([]);
      setCatalogNextCursor(undefined);
      setCatalogInitialized(false);
      setCatalogOpen(false);
    }
    setScreen("search");
  };
  const openSearchFromNav = () => {
    leaveWork();
    setSection("search");
    setSearchOrigin("normal");
    setScreen("search");
  };
  const back = () => {
    leaveWork();
    cancel();
  };
  const openSaved = () => {
    leaveWork();
    setSection("saved");
    setScreen("saved");
  };
  const capture = () => {
    const video = videoRef.current,
      canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) {
      cameraRef.current?.click();
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob)
          pickPhoto(new File([blob], "camera.jpg", { type: "image/jpeg" }));
        else cameraRef.current?.click();
      },
      "image/jpeg",
      0.9,
    );
  };
  const discardRetainedPhoto = () => {
    setExpandedPhoto(false);
    setPhoto(undefined);
    setPhotoFile(undefined);
    setReceipt(undefined);
    setCandidates([]);
    setSelected(undefined);
    resetFeedback();
    lastRequest.current = { scenario, hasPhoto: false };
  };
  const choose = (c: Candidate) => {
    listScroll.current = contentRef.current?.scrollTop ?? 0;
    window.history.pushState({ ...window.history.state, brutforceCandidateResult: true }, "");
    candidateResultHistory.current = true;
    setSelected(c);
    if (candidateOrigin !== "correction") setResultOrigin(candidateOrigin);
    setResultFromCorrection(candidateOrigin === "correction");
    setResultHasPhoto(candidateHasPhoto);
    setScreen("result");
  };
  const chooseCatalog = (c: Candidate) => {
    invalidateCatalogWork();
    listScroll.current = contentRef.current?.scrollTop ?? 0;
    window.history.pushState({ ...window.history.state, brutforceCandidateResult: true }, "");
    candidateResultHistory.current = true;
    setSelected(c);
    setCandidates([]);
    setResultOrigin("catalog");
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setScreen("result");
  };
  const chooseSaved = (c: Candidate) => {
    listScroll.current = contentRef.current?.scrollTop ?? 0;
    window.history.pushState({ ...window.history.state, brutforceCandidateResult: true }, "");
    candidateResultHistory.current = true;
    setSelected(c);
    setCandidates([]);
    setResultOrigin("saved");
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setScreen("result");
  };
  const chooseRecommendation = (c: Candidate) => {
    setSelected(c);
    setResultHasPhoto(false);
    setResultFromCorrection(false);
  };
  const backFromCandidates = () => {
    if (candidateOrigin === "correction") {
      setSection("search");
      setSearchOrigin("correction");
      setScreen("search");
      return;
    }
    if (candidateOrigin === "manual") {
      setSection("search");
      setSearchOrigin("normal");
      setScreen("search");
      return;
    }
    back();
  };
  const backFromResult = () => {
    if (candidateResultHistory.current) {
      candidateResultHistory.current = false;
      window.history.back();
      if (resultOrigin === "catalog") {
        setSection("search");
        setScreen("search");
      } else if (resultOrigin === "saved") {
        setSection("saved");
        setScreen("saved");
      } else {
        setCandidateHasPhoto(resultHasPhoto);
        setScreen("candidates");
      }
      return;
    }
    if (resultFromCorrection) {
      setCandidateOrigin("correction");
      setScreen("candidates");
      return;
    }
    if (resultOrigin === "manual") {
      setCandidateOrigin("manual");
      setCandidateHasPhoto(resultHasPhoto);
      setScreen("candidates");
      return;
    }
    if (resultOrigin === "catalog") {
      setSection("search");
      setScreen("search");
      return;
    }
    if (resultOrigin === "saved") {
      setSection("saved");
      setScreen("saved");
      return;
    }
    back();
  };
  useEffect(() => {
    const onPopState = () => {
      if (screen !== "result" || !candidateResultHistory.current) return;
      candidateResultHistory.current = false;
      if (resultOrigin === "catalog") {
        setSection("search");
        setScreen("search");
      } else if (resultOrigin === "saved") {
        setSection("saved");
        setScreen("saved");
      } else {
        setCandidateHasPhoto(resultHasPhoto);
        setScreen("candidates");
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [candidateOrigin, resultHasPhoto, resultOrigin, screen]);
  const backFromSearch = () => {
    back();
  };
  useEffect(() => {
    try {
      const raw = localStorage.getItem(savedKey);
      if (!raw) return;
      const value: unknown = JSON.parse(raw);
      if (!isCandidateList(value)) throw new Error();
      setSaved(value);
    } catch {
      try {
        localStorage.removeItem(savedKey);
      } catch {}
      setStorageNotice("Сохранённый список был повреждён и очищен.");
    }
  }, []);
  const invalidateCatalogWork = () => {
    catalogGeneration.current += 1;
    catalogAbort.current?.abort();
    if (catalogTimer.current) clearTimeout(catalogTimer.current);
    catalogTimer.current = undefined;
    setCatalogDebouncing(false);
    setCatalogLoading(false);
  };
  const loadCatalog = (next: { append?: boolean; q?: string } = {}) => {
    catalogAbort.current?.abort();
    const controller = new AbortController();
    const generation = catalogGeneration.current;
    catalogAbort.current = controller;
    setCatalogError("");
    setCatalogFailedAppend(false);
    setCatalogStaleCursor(false);
    setCatalogLoading(true);
    setCatalogInitialized(true);
    const q = next.q ?? catalogQuery;
    getCatalog({ limit: 24, cursor: next.append ? catalogNextCursor : undefined, q, signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted && catalogAbort.current === controller && generation === catalogGeneration.current) {
          setCatalogDemo(data.demo);
          setCatalog((current) => next.append ? [...current, ...data.candidates] : data.candidates);
          if (!next.append) setCatalogDisplayedQuery(q);
          setCatalogNextCursor(data.nextCursor);
          setCatalogVersion(data.catalogVersion);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted && catalogAbort.current === controller && generation === catalogGeneration.current && (error as Error).name !== "AbortError") {
          const stale = error instanceof StaleCatalogCursorError;
          setCatalogStaleCursor(stale);
          setCatalogFailedAppend(Boolean(next.append) && !stale);
          setCatalogError(stale ? "Каталог обновился. Обновите результаты текущего поиска." : next.append ? "Не удалось загрузить ещё вина." : "Не удалось загрузить вина");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && catalogAbort.current === controller && generation === catalogGeneration.current)
          setCatalogLoading(false);
      });
  };
  useEffect(() => {
    if (screen !== "search" || catalog.length || !catalogOpen || catalogInitialized) return;
    loadCatalog({ q: catalogQuery });
  }, [screen, catalog.length, catalogOpen, catalogQuery, catalogInitialized]);
  const requestCatalogNow = (value = query) => {
    const nextQuery = value.trim();
    if (catalogComposing.current || (catalogLoading && catalogQuery === nextQuery && catalogAbort.current && !catalogAbort.current.signal.aborted)) return;
    invalidateCatalogWork();
    setCatalogQuery(nextQuery);
    setCatalogNextCursor(undefined);
    setCatalogOpen(true);
    setCatalogInitialized(true);
    setCatalogLoading(false);
    if (screen !== "search") setScreen("search");
    lastRequest.current = { scenario, query: nextQuery, hasPhoto: false };
    loadCatalog({ q: nextQuery });
  };
  const scheduleCatalogSearch = (value: string) => {
    if (value === query) return;
    setQuery(value);
    const nextQuery = value.trim();
    invalidateCatalogWork();
    setCatalogQuery(nextQuery);
    setCatalogNextCursor(undefined);
    setCatalogOpen(true);
    setCatalogInitialized(true);
    setCatalogError("");
    if (!nextQuery) {
      setCatalogLoading(false);
      loadCatalog({ q: "" });
      return;
    }
    setCatalogDebouncing(true);
    const generation = catalogGeneration.current;
    catalogTimer.current = setTimeout(() => {
      if (generation !== catalogGeneration.current) return;
      catalogTimer.current = undefined;
      setCatalogDebouncing(false);
      loadCatalog({ q: nextQuery });
    }, 250);
  };
  const updateCatalogQuery = (nextQuery: string) => scheduleCatalogSearch(nextQuery);
  const submitCatalogSearch = () => requestCatalogNow();
  const shown = selected;
  const newIdempotencyKey = () => {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  };
  const submitFeedback = async (decision: FeedbackDecision, displayed?: Candidate) => {
    if (!feedbackToken || feedbackMode === "saving" || feedbackMode === "saved") return;
    if (decision === "correct" && !feedbackTarget) {
      setFeedbackError("Выберите правильное вино из каталога.");
      return;
    }
    if (!feedbackIdempotency.current) feedbackIdempotency.current = newIdempotencyKey();
    const generation = feedbackGeneration.current;
    setFeedbackMode("saving");
    setFeedbackError("");
    try {
      const saved = await savePhotoFeedback({
        feedbackToken,
        idempotencyKey: feedbackIdempotency.current,
        decision,
        ...(displayed ? { displayedWineId: displayed.id } : {}),
        ...(decision === "correct" ? { correctWineId: feedbackTarget?.id } : {}),
        ...(feedbackComment.trim() ? { comment: feedbackComment.trim() } : {}),
      });
      if (generation !== feedbackGeneration.current) return;
      setFeedbackReceipt(saved);
      setFeedbackMode("saved");
    } catch (error) {
      if (generation !== feedbackGeneration.current) return;
      setFeedbackError((error as Error).message);
      setFeedbackMode("error");
    }
  };
  const loadFeedbackCatalog = async (append = false) => {
    feedbackCatalogAbort.current?.abort();
    const controller = new AbortController();
    feedbackCatalogAbort.current = controller;
    const generation = feedbackGeneration.current;
    setFeedbackCatalogLoading(true);
    setFeedbackCatalogError("");
    try {
      const data = await getCatalog({ limit: 12, cursor: append ? feedbackCatalogCursor : undefined, q: feedbackQuery.trim(), signal: controller.signal });
      if (controller.signal.aborted || generation !== feedbackGeneration.current || feedbackCatalogAbort.current !== controller) return;
      setFeedbackCatalog(current => append ? [...current, ...data.candidates] : data.candidates);
      setFeedbackCatalogCursor(data.nextCursor);
    } catch (error) {
      if ((error as Error).name === "AbortError" || generation !== feedbackGeneration.current) return;
      setFeedbackCatalogError("Не удалось загрузить каталог.");
    } finally {
      if (!controller.signal.aborted && generation === feedbackGeneration.current && feedbackCatalogAbort.current === controller) setFeedbackCatalogLoading(false);
    }
  };
  const persistSaved = (next: Candidate[], success: string) => {
    try {
      localStorage.setItem(savedKey, JSON.stringify(next));
      setSaved(next);
      setStorageNotice(success);
    } catch {
      setStorageNotice("Не удалось сохранить изменения в этом браузере.");
    }
  };
  const toggleSaved = (wine: Candidate) => {
    const exists = saved.some((item) => item.id === wine.id);
    persistSaved(
      exists ? saved.filter((item) => item.id !== wine.id) : [...saved, wine],
      exists ? "Удалено из сохранённых." : "Сохранено в этом браузере.",
    );
  };
  const showNav = !expandedPhoto;

  return (
    <main className="app-shell">
      <section className={`app${screen === "camera" ? " camera-open" : ""}`} data-testid="app">
        <div className="app-content" ref={contentRef}>
          {screen === "welcome" && (
            <Page id="UI-001">
              <div className="welcome-intro">
                <header className="brand v2-brand">
                  <V2Logo />
                </header>
                <div className="hero">
                  <div>
                    <h1>
                      Какое вино перед вами?
                    </h1>
                    <p>Сфотографируйте этикетку.<br />Откроем карточку вина.</p>
                  </div>
                  <MascotScene scene="home" />
                </div>
              </div>
              <div className="actions">
                <button className="primary scan-button" onClick={openCamera}>
                  <Camera />
                  <span>
                    <b>Сканировать вино</b>
                  </span>
                  <AtlasScan />
                </button>
                <div className="split-actions">
                  <button onClick={() => galleryRef.current?.click()}>
                    <ImageSquare />
                    Выбрать фото
                  </button>
                  <button onClick={openSearch}>
                    <MagnifyingGlass />
                    По названию
                  </button>
                </div>
              </div>
              <InstallApp />
            </Page>
          )}
          {screen === "camera" && (
            <div className="camera-page" id="UI-002">
              <div className="camera-header">
                <Top title="Этикетка вина" onBack={backFromCamera} />
                <p>Нужная бутылка по центру</p>
              </div>
              <div className="camera-preview">
                <div className="viewfinder">
                  <video
                    ref={videoRef}
                    playsInline
                    muted
                    aria-label="Изображение с камеры"
                  />
                  <div className="camera-frame" />
                </div>
              </div>
              <canvas ref={canvasRef} hidden />
              <div className="camera-actions">
                <button
                  className="camera-gallery-action"
                  aria-label="Выбрать из галереи"
                  onClick={() => galleryRef.current?.click()}
                >
                  <ImageSquare weight="light" />
                </button>
                <button
                  className="shutter"
                  aria-label="Сделать снимок"
                  onClick={capture}
                >
                  <span />
                </button>
                <span aria-hidden="true" />
              </div>
            </div>
          )}
          {screen === "permission" && (
            <Page id="UI-003">
              <Top title="Доступ к камере" onBack={backFromCamera} />
              <StateIcon>
                <Camera />
              </StateIcon>
              <h2>Камера недоступна</h2>
              <p>
                Можно продолжить с фотографией из галереи или найти вино по
                названию.
              </p>
              <button
                className="primary"
                onClick={() => galleryRef.current?.click()}
              >
                <ImageSquare />
                Выбрать фото
              </button>
              <button
                className="secondary"
                onClick={() => setScreen("settings")}
              >
                Как разрешить камеру
              </button>
              <button className="text-button" onClick={openSearch}>
                Найти по названию
              </button>
            </Page>
          )}
          {screen === "settings" && (
            <Page id="UI-003A">
              <Top
                title="Разрешить камеру"
                onBack={() => setScreen("permission")}
              />
              <h2>Проверьте доступ в браузере</h2>
              <p>
                Откройте настройки сайта, разрешите камеру и вернитесь к
                сканированию. Название пункта зависит от браузера.
              </p>
              <button className="primary" onClick={() => setScreen("camera")}>
                Вернуться к камере
              </button>
              <button
                className="secondary"
                onClick={() => galleryRef.current?.click()}
              >
                Выбрать фото
              </button>
            </Page>
          )}
          {(screen === "loading" || screen === "waiting") && (
            <Page id="UI-004">
              <Top title="Поиск" onBack={cancel} />
              <h2>
                {screen === "waiting"
                  ? "Нужно ещё немного времени"
                  : "Ищем ваше вино"}
              </h2>
              <p>
                {screen === "waiting"
                  ? "Проверяем похожие записи в каталоге."
                  : "Сверяем снимок с винами в каталоге."}
              </p>
              <MascotScene scene="walk" />
              <div className="air-waiting-discovery">
              {photo && lastRequest.current.hasPhoto && (
                <div className="air-waiting-photo">
                  <Photo photo={photo} onExpand={() => setExpandedPhoto(true)} />
                  <div className="air-scan-viewport" aria-hidden="true"><div className="scan-line" /></div>
                </div>
              )}
              <aside className="air-wine-note" aria-label="Заметка о вине">
                <div className="air-wine-note-header">
                  <span>О вине</span>
                  <button className="air-note-toggle" aria-label={notePaused ? "Продолжить заметки" : "Приостановить заметки"} aria-pressed={notePaused} onClick={() => setNotePaused((paused) => !paused)}>
                    {notePaused ? <Play weight="light" /> : <Pause weight="light" />}
                  </button>
                </div>
                <p key={noteIndex}>{wineNotes[noteIndex]}</p>
              </aside>
              </div>
              <p className="status" role="status">
                {screen === "waiting" ? "Продолжаем поиск" : "Ищем совпадения"}
              </p>
              <button className="text-button bottom" onClick={cancel}>
                Отменить поиск
              </button>
            </Page>
          )}
          {screen === "candidates" && (
            <Page id="UI-006">
              <Top title="Результат поиска" onBack={backFromCandidates} />
              <h2>{candidates.length === 1 ? "Проверьте найденное вино" : "Нашли похожие вина"}</h2>
              <p>
                {candidateHasPhoto
                  ? "Сверьте название и винодельню со своим снимком."
                  : "Сравните название, винодельню и год."}
              </p>
              {demoMode && <DemoDisclosure />}
              {photo && candidateHasPhoto && <div className="air-comparison">
                <Photo photo={photo} compact onExpand={() => setExpandedPhoto(true)} />
                <div className="air-comparison-actions" role="group" aria-label="Заменить снимок">
                  <button className="air-photo-action" aria-label="Сделать новый снимок" onClick={newCapture}><Camera weight="light" /></button>
                  <button className="air-photo-action" aria-label="Галерея" onClick={() => galleryRef.current?.click()}><ImageSquare weight="light" /></button>
                </div>
              </div>}
              <WineList
                wines={candidates}
                onChoose={choose}
                leader
              />
              {catalogNextCursor && candidateOrigin === "manual" && (
                <button className="secondary" disabled={catalogLoading} onClick={() => loadCatalog({ append: true })}>
                  {catalogLoading ? "Загружаем…" : "Показать ещё"}
                </button>
              )}
              <button className="secondary" onClick={() => { setMissingReason("rejected"); setScreen("missing"); }}>
                Ни одно не подходит
              </button>
            </Page>
          )}
          {screen === "result" &&
            shown &&
            (() => {
              const isSaved = saved.some((item) => item.id === shown.id);
              const sourceUrl = safeSourceUrl(shown.sourceUrl);
              const strength = alcoholLabel(shown);
              const region = shown.region?.filter((value) => value.trim()).join(", ");
              return (
                <Page id="UI-007">
                  <Top
                    title="Карточка вина"
                    onBack={backFromResult}
                    action={
                      <button
                        className="save-header-action"
                        aria-label={
                          isSaved ? "Удалить из сохранённых" : "Сохранить вино"
                        }
                        aria-pressed={isSaved}
                        onClick={() => toggleSaved(shown)}
                      >
                        <BookmarkSimple weight={isSaved ? "fill" : "regular"} />
                        <span>{isSaved ? "Сохранено" : "Сохранить"}</span>
                      </button>
                    }
                  />
                  <div className="result-hero">
                    <div className="result-shelf">
                      <CandidateImage candidate={shown} role="card" priority />
                      {(shown.sugar?.trim() || strength || region) && (
                        <div className="result-facts" aria-label="Основные характеристики">
                          {shown.sugar?.trim() && <div className="result-fact"><IconDroplet aria-hidden="true" /><span>{shown.sugar}</span></div>}
                          {strength && <div className="result-fact"><IconGlassFull aria-hidden="true" /><span>{strength}</span></div>}
                          {region && <div className="result-fact"><IconMapPin aria-hidden="true" /><span>{region}</span></div>}
                        </div>
                      )}
                    </div>
                    {(resultOrigin === "catalog" ? catalogDemo : demoMode) && <span className="demo-label"><Check />{resultOrigin === "catalog" ? "Демо-карточка" : "Reference"}</span>}
                    <p className="result-winery">{shown.winery}{hasYear(shown.year) && <>{shown.winery && " · "}{shown.year}</>}</p>
                    <h2>{shown.name}</h2>
                    {sourceUrl && <a className="result-source" href={sourceUrl} target="_blank" rel="noopener noreferrer" aria-label="Открыть на сайте «Своё Вино» в новой вкладке">Открыть на сайте «Своё Вино» <span aria-hidden="true">↗</span></a>}
                  </div>
                  {storageNotice && (
                    <p className="storage-notice" role="status">
                      {storageNotice}
                    </p>
                  )}
                  {demoMode && <DemoDisclosure />}
                  <dl className="result-overview">
                    <div><dt>Винодельня</dt><dd>{shown.winery}</dd></div>
                    <div><dt>Год</dt><dd>{displayYear(shown.year)}</dd></div>
                    {region && <div><dt>Регион</dt><dd>{region}</dd></div>}
                    {shown.grapes?.length ? <div><dt>Сорт винограда</dt><dd>{shown.grapes.join(", ")}</dd></div> : null}
                    {shown.categoryAndSweetness ? <div><dt>Категория</dt><dd>{shown.categoryAndSweetness}</dd></div> : null}
                    {shown.color ? <div><dt>Цвет</dt><dd>{shown.color}</dd></div> : null}
                    {shown.sugar?.trim() ? <div><dt>Сахар</dt><dd>{shown.sugar}</dd></div> : null}
                    {strength && <div><dt>Алкоголь</dt><dd>{strength}</dd></div>}
                    {isPositiveFinite(shown.volumeL) ? <div><dt>Объём</dt><dd>{shown.volumeL} л</dd></div> : null}
                  </dl>
                  {shown.description.trim() && <details className="result-description" key={shown.id}>
                    <summary>О вкусе и сочетаниях</summary>
                    <p>{shown.description}</p>
                  </details>}
                  {resultHasPhoto && feedbackToken && (
                    <section className="photo-feedback" aria-labelledby="photo-feedback-title">
                      <h3 id="photo-feedback-title">Разметить мою фотографию</h3>
                      <p>Подтвердите результат или укажите правильную позицию. Ответ сохранится отдельно для проверки и последующего дообучения.</p>
                      {feedbackMode === "saved" ? (
                        <div className="feedback-success" role="status">
                          <Check />
                          <span><b>Разметка сохранена</b><small>Квитанция {feedbackReceipt?.feedbackId.slice(0, 8)}</small></span>
                        </div>
                      ) : <>
                        <label htmlFor="feedback-comment">Комментарий — необязательно</label>
                        <textarea id="feedback-comment" maxLength={2000} disabled={feedbackMode === "saving"} value={feedbackComment} onChange={event => { setFeedbackComment(event.target.value); if (feedbackMode === "error") feedbackIdempotency.current = ""; }} placeholder="Например: другой год, редизайн этикетки…" />
                        <div className="feedback-actions">
                          <button className="primary" disabled={feedbackMode === "saving"} onClick={() => submitFeedback("confirm", shown)}>
                            {feedbackMode === "saving" ? "Сохраняем…" : "Подтвердить"}
                          </button>
                          <button className="secondary" disabled={feedbackMode === "saving"} onClick={() => { setFeedbackMode("correcting"); setFeedbackError(""); feedbackIdempotency.current = ""; if (!feedbackCatalog.length) void loadFeedbackCatalog(); }}>
                            Нет, это другое вино
                          </button>
                        </div>
                        {(feedbackMode === "correcting" || feedbackTarget) && (
                          <div className="feedback-correction">
                            <label htmlFor="feedback-wine-search">Какое это вино?</label>
                            <div className="search-field">
                              <input id="feedback-wine-search" value={feedbackQuery} onChange={event => setFeedbackQuery(event.target.value)} placeholder="Название или винодельня" />
                              <button aria-label="Найти правильное вино" onClick={() => { setFeedbackTarget(undefined); feedbackIdempotency.current = ""; void loadFeedbackCatalog(); }}><MagnifyingGlass /></button>
                            </div>
                            {feedbackTarget && <div className="feedback-target"><span><small>Выбрано</small><b>{feedbackTarget.name}</b><small>{feedbackTarget.winery}</small></span><button className="text-button" onClick={() => { setFeedbackTarget(undefined); feedbackIdempotency.current = ""; }}>Изменить</button></div>}
                            {!feedbackTarget && <div className="feedback-catalog" aria-label="Результаты поиска правильного вина">
                              {feedbackCatalog.map(wine => <button key={wine.id} onClick={() => { setFeedbackTarget(wine); setFeedbackError(""); feedbackIdempotency.current = ""; }}><CandidateImage candidate={wine} role="card" /><span><b>{wine.name}</b><small>{wine.winery}</small></span></button>)}
                            </div>}
                            {feedbackCatalogCursor && !feedbackTarget && <button className="text-button" disabled={feedbackCatalogLoading} onClick={() => void loadFeedbackCatalog(true)}>Показать ещё</button>}
                            {feedbackCatalogLoading && <p role="status">Загружаем каталог…</p>}
                            {feedbackCatalogError && <p role="alert">{feedbackCatalogError}</p>}
                            <button className="primary" disabled={!feedbackTarget || feedbackMode === "saving"} onClick={() => submitFeedback("correct", shown)}>Сохранить исправление</button>
                          </div>
                        )}
                        {feedbackError && <p className="feedback-error" role="alert">{feedbackError}</p>}
                      </>}
                    </section>
                  )}
                  <section className="recommendations" aria-labelledby="recommendations-title">
                    <h3 id="recommendations-title">Вам также может подойти</h3>
                    {recommendations.status === "loading" && (
                      <p role="status">Подбираем рекомендации</p>
                    )}
                    {recommendations.status === "ready" && (
                      <RecommendationList
                        wines={recommendations.candidates}
                        onChoose={chooseRecommendation}
                      />
                    )}
                    {recommendations.status === "empty" && (
                      <p>Пока нет рекомендаций для этой карточки.</p>
                    )}
                    {recommendations.status === "error" && (
                      <div className="recommendation-error" role="alert">
                        <p>Не удалось загрузить рекомендации.</p>
                        <button
                          className="secondary"
                          onClick={() => setRecommendationAttempt((attempt) => attempt + 1)}
                        >
                          Повторить рекомендации
                        </button>
                      </div>
                    )}
                  </section>
                  <div className="result-actions">
                    <button className="primary" onClick={newCapture}>
                      Сканировать ещё
                    </button>
                    {photo && resultHasPhoto && (
                      <button
                        className="text-button"
                        onClick={() => setExpandedPhoto(true)}
                      >
                        Сверить с моим фото
                      </button>
                    )}
                  </div>
                </Page>
              );
            })()}
          {screen === "search" && (
            <Page id="UI-008">
              <Top title="Поиск по названию" onBack={backFromSearch} />
              <h2>Найдём по названию</h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (query.trim() && !catalogComposing.current) {
                    searchScroll.current = contentRef.current?.scrollTop ?? 0;
                    submitCatalogSearch();
                  }
                }}
              >
                <label htmlFor="query">Название вина или винодельня</label>
                <div className={`search-field${query ? " has-clear" : ""}`}>
                  <input
                    id="query"
                    ref={queryRef}
                    value={query}
                    onChange={(e) => updateCatalogQuery(e.target.value)}
                    onCompositionStart={() => { catalogComposing.current = true; }}
                    onCompositionEnd={(e) => {
                      if (!catalogComposing.current) return;
                      catalogComposing.current = false;
                      if (e.currentTarget.value !== query) scheduleCatalogSearch(e.currentTarget.value);
                    }}
                    placeholder="Например, Каберне"
                  />
                  {query && <button className="clear-search" aria-label="Очистить поиск" type="button" onClick={() => { catalogComposing.current = false; scheduleCatalogSearch(""); queryRef.current?.focus(); }}>×</button>}
                  <button aria-label="Искать" type="submit">
                    <MagnifyingGlass />
                  </button>
                </div>
              </form>
              {!query && !catalogOpen && (
                <div className="manual-empty">
                  <p>
                    Введите название или винодельню — либо откройте весь
                    каталог.
                  </p>
                  <div className="air-search-mascot"><MascotScene scene="browse" /></div>
                  <button
                    className="secondary"
                    onClick={() => setCatalogOpen(true)}
                  >
                    Открыть каталог
                  </button>
                </div>
              )}
              {(catalogQuery || catalogOpen) && <>
                {(() => {
                  const olderResults = catalog.length > 0 && catalogQuery !== catalogDisplayedQuery;
                  const status = catalogDebouncing || catalogLoading
                    ? olderResults ? "Обновляем · ниже прежние результаты" : catalogDebouncing ? "Обновляем результаты…" : "Ищем вина…"
                    : olderResults ? "Показаны прежние результаты" : catalog.length ? `Показано ${catalog.length}` : "";
                  return <div className="catalog-status" role="status" aria-live="polite" aria-label={status}>{status}</div>;
                })()}
                {catalog.length ? <WineList wines={catalog} onChoose={chooseCatalog} leader={Boolean(catalogDisplayedQuery)} /> : null}
                {catalogError ? (
                  <div className="catalog-error" role="alert" aria-label="Не удалось загрузить вина">
                    <p>{catalogError}{catalog.length && catalogQuery !== catalogDisplayedQuery ? " Показаны прежние результаты." : ""}</p>
                    <button className="secondary" onClick={() => catalogStaleCursor ? requestCatalogNow(catalogQuery) : loadCatalog({ q: catalogQuery, append: catalogFailedAppend })}>{catalogStaleCursor ? "Обновить результаты" : "Повторить"}</button>
                  </div>
                ) : !catalog.length && !catalogLoading && !catalogDebouncing && catalogInitialized ? (
                  <div className="empty-catalog"><p>Не нашли вина по этому запросу</p><p>Попробуйте другое название или винодельню</p></div>
                ) : null}
                {catalogNextCursor && !catalogStaleCursor && (!catalogError || catalog.length > 0) && (
                  <button className="secondary" disabled={catalogLoading || catalogDebouncing} onClick={() => loadCatalog({ append: true })}>
                    {catalogLoading ? "Загружаем…" : "Показать ещё"}
                  </button>
                )}
              </>}
              <button className="text-button" onClick={newCapture}>
                <Camera weight="light" />
                Сканировать этикетку
              </button>
              <ProductFooter />
            </Page>
          )}
          {screen === "saved" && (
            <Page id="UI-016">
              <Top title="Сохранённое" onBack={back} />
              <header className="saved-heading">
                <h2>Сохранённое</h2>
                <p>Только в этом браузере, без аккаунта.</p>
              </header>
              {storageNotice && (
                <p className="storage-notice" role="status">
                  {storageNotice}
                </p>
              )}
              {saved.length ? (
                <WineList wines={saved} onChoose={chooseSaved} />
              ) : (
                <div className="saved-empty">
                  <figure className="mascot-scene mascot-scene-saved" aria-hidden="true">
                    <img src="/assets/v2/mascot-hold-2d-alpha.webp" alt="" />
                  </figure>
                  <h3>Пока ничего не сохранено</h3>
                  <p>Откройте карточку вина и нажмите «Сохранить вино».</p>
                  <button className="primary" onClick={() => { openSearch(); setCatalogOpen(true); }}>
                    Открыть каталог
                  </button>
                </div>
              )}
              <ProductFooter />
            </Page>
          )}
          {screen === "missing" && (
            <Page id="UI-009">
              <Top
                title="Результат поиска"
                onBack={() => {
                  if (missingReason === "rejected") setScreen("candidates");
                  else back();
                }}
              />
              <h2>{missingReason === "rejected"
                ? "Ни одно вино не подошло"
                : missingReason === "outside_display"
                  ? "Карточка пока недоступна"
                  : "Ничего не найдено"}</h2>
              <p>{missingReason === "rejected"
                ? "Попробуйте поиск по названию или другой снимок."
                : missingReason === "outside_display"
                  ? "Вино распознано, но его карточки пока нет в нашем каталоге."
                  : "Сервис не нашёл подходящего совпадения."}</p>
              {photo && lastRequest.current.hasPhoto && (
                <RecoveryPhoto photo={photo} onExpand={() => setExpandedPhoto(true)} onCamera={newCapture} onGallery={() => galleryRef.current?.click()} />
              )}
              {photo && lastRequest.current.hasPhoto && feedbackToken && (
                <section className="photo-feedback" aria-labelledby="missing-feedback-title">
                  <h3 id="missing-feedback-title">Разметить мою фотографию</h3>
                  {feedbackMode === "saved" ? (
                    <div className="feedback-success" role="status">
                      <Check />
                      <span><b>Разметка сохранена</b><small>Квитанция {feedbackReceipt?.feedbackId.slice(0, 8)}</small></span>
                    </div>
                  ) : <>
                    <p>Если вино есть в каталоге, укажите правильную карточку.</p>
                    <label htmlFor="missing-feedback-comment">Комментарий — необязательно</label>
                    <textarea id="missing-feedback-comment" maxLength={2000} disabled={feedbackMode === "saving"} value={feedbackComment} onChange={event => { setFeedbackComment(event.target.value); if (feedbackMode === "error") feedbackIdempotency.current = ""; }} placeholder="Например: модель не распознала новый дизайн…" />
                    {feedbackMode !== "correcting" && !feedbackTarget && (
                      <button className="secondary" onClick={() => { setFeedbackMode("correcting"); setFeedbackError(""); feedbackIdempotency.current = ""; if (!feedbackCatalog.length) void loadFeedbackCatalog(); }}>
                        Указать правильное вино
                      </button>
                    )}
                    {(feedbackMode === "correcting" || feedbackTarget) && (
                      <div className="feedback-correction">
                        <label htmlFor="missing-feedback-wine-search">Какое это вино?</label>
                        <div className="catalog-search feedback-search">
                          <input id="missing-feedback-wine-search" value={feedbackQuery} onChange={event => setFeedbackQuery(event.target.value)} placeholder="Название или винодельня" />
                          <button aria-label="Найти правильное вино" onClick={() => { setFeedbackTarget(undefined); feedbackIdempotency.current = ""; void loadFeedbackCatalog(); }}><MagnifyingGlass /></button>
                        </div>
                        {feedbackTarget && <div className="feedback-target"><span><small>Выбрано</small><b>{feedbackTarget.name}</b><small>{feedbackTarget.winery}</small></span><button className="text-button" onClick={() => { setFeedbackTarget(undefined); feedbackIdempotency.current = ""; }}>Изменить</button></div>}
                        {!feedbackTarget && <div className="feedback-catalog" aria-label="Результаты поиска правильного вина">
                          {feedbackCatalog.map(wine => <button key={wine.id} onClick={() => { setFeedbackTarget(wine); setFeedbackError(""); feedbackIdempotency.current = ""; }}><CandidateImage candidate={wine} role="card" /><span><b>{wine.name}</b><small>{wine.winery}</small></span></button>)}
                        </div>}
                        {feedbackCatalogCursor && !feedbackTarget && <button className="text-button" disabled={feedbackCatalogLoading} onClick={() => void loadFeedbackCatalog(true)}>Показать ещё</button>}
                        {feedbackCatalogLoading && <p role="status">Загружаем каталог…</p>}
                        {feedbackCatalogError && <p role="alert">{feedbackCatalogError}</p>}
                        <button className="primary" disabled={!feedbackTarget || feedbackMode === "saving"} onClick={() => submitFeedback("correct")}>Сохранить разметку</button>
                      </div>
                    )}
                    {feedbackError && <p className="feedback-error" role="alert">{feedbackError}</p>}
                  </>}
                </section>
              )}
              <MascotScene scene="counter" />
              {lastRequest.current.hasPhoto ? (
                <div className="missing-actions">
                  <button className="primary" onClick={openSearch}>
                    Найти по названию
                  </button>
                </div>
              ) : (
                <div className="missing-actions">
                  <button
                    className="primary"
                    onClick={() => {
                      setSection("search");
                      setScreen("search");
                    }}
                  >
                    Изменить запрос
                  </button>
                </div>
              )}
            </Page>
          )}
          {screen === "error" && (
            <Page id="UI-010">
              <Top title="Ошибка поиска" onBack={back} />
              {errorKind === "network" ? <MascotScene scene="offline" /> : (
                <figure className="mascot-scene mascot-scene-server" aria-hidden="true">
                  <img src="/assets/v2/server-error-a.png" alt="" />
                </figure>
              )}
              <h2>
                {errorKind === "network"
                  ? "Похоже, нет сети"
                  : "Не удалось получить ответ"}
              </h2>
              <p>
                {errorKind === "network"
                  ? "Проверьте подключение к интернету и повторите попытку."
                  : "Сервер не смог завершить поиск. Повторите попытку позже."}
                {photo && lastRequest.current.hasPhoto
                  ? " Снимок сохранён в этой вкладке."
                  : ""}
              </p>
              {photo && lastRequest.current.hasPhoto && (
                <RecoveryPhoto photo={photo} onExpand={() => setExpandedPhoto(true)} onCamera={newCapture} onGallery={() => galleryRef.current?.click()} />
              )}
              <button className="primary" onClick={retry}>
                {errorKind === "network" ? "Проверить ещё раз" : "Повторить поиск"}
              </button>
            </Page>
          )}
          {screen === "badphoto" && (
            <Page id="UI-011">
              <Top title="Неподходящий файл" onBack={backFromCamera} />
              <StateIcon>
                <ImageSquare />
              </StateIcon>
              <h2>Нужно изображение</h2>
              <p>Выберите JPEG, PNG или GIF размером не более 10 МБ.</p>
              <button
                className="primary"
                onClick={() => galleryRef.current?.click()}
              >
                Выбрать другое фото
              </button>
              <button className="secondary" onClick={newCapture}>Камера</button>
              <button className="text-button" onClick={openSearch}>По названию</button>
            </Page>
          )}
          <input
            ref={cameraRef}
            className="visually-hidden"
            aria-label="Снять фотографию этикетки"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => {
              pickPhoto(e.target.files?.[0]);
              e.currentTarget.value = "";
            }}
          />
          <input
            ref={galleryRef}
            className="visually-hidden"
            aria-label="Загрузить фотографию этикетки"
            type="file"
            accept="image/*"
            onChange={(e) => {
              pickPhoto(e.target.files?.[0]);
              e.currentTarget.value = "";
            }}
          />
          {expandedPhoto && photo && (
            <div
              className="photo-dialog"
              role="dialog"
              aria-modal="true"
              aria-label="Исходная фотография"
            >
              <button
                className="dialog-close"
                aria-label="Закрыть фотографию"
                onClick={() => setExpandedPhoto(false)}
              >
                <X />
              </button>
              <img
                src={photo}
                alt="Исходная фотография этикетки крупным планом"
              />
              <div className="dialog-actions">
                <button onClick={newCapture}>Переснять</button>
                {!["loading", "waiting"].includes(screen) && (
                  <button
                    onClick={() => {
                      setExpandedPhoto(false);
                      retry();
                    }}
                  >
                    Повторить поиск
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        {showNav && (
          <BottomNav
            section={section}
            onHome={back}
            onSearch={openSearchFromNav}
            onSaved={openSaved}
          />
        )}
      </section>
    </main>
  );
}

function Page({ children, id }: { children: React.ReactNode; id: string }) {
  return (
    <div className="page" id={id} data-testid={id}>
      {children}
    </div>
  );
}
function Top({
  title,
  onBack,
  action,
}: {
  title: string;
  onBack: () => void;
  action?: React.ReactNode;
}) {
  return (
    <header className={`top${action ? " top-with-action" : ""}`}>
      <button aria-label="Назад" onClick={onBack}>
        <ArrowLeft />
      </button>
      <b>{title}</b>
      {action ?? <span />}
    </header>
  );
}
function DemoDisclosure() {
  return (
    <aside className="demo-disclosure" role="note" aria-label="Reference-режим">
      <strong>Reference-режим</strong>
      <span>Распознавание показывает справочные варианты; результат не является измеренной модельной оценкой.</span>
    </aside>
  );
}
function StateIcon({ children }: { children: React.ReactNode }) {
  return <div className="state-icon">{children}</div>;
}
function Photo({
  photo,
  compact = false,
  onExpand,
}: {
  photo: string;
  compact?: boolean;
  onExpand?: () => void;
}) {
  return (
    <button
      type="button"
      className={`photo ${compact ? "compact" : ""}`}
      onClick={onExpand}
      aria-label={onExpand ? "Открыть исходную фотографию" : undefined}
    >
      <img src={photo} alt="Загруженная фотография этикетки" />
      <span>Ваше фото</span>
    </button>
  );
}
function RecoveryPhoto({ photo, onExpand, onCamera, onGallery }: {
  photo: string;
  onExpand: () => void;
  onCamera: () => void;
  onGallery: () => void;
}) {
  return <div className="air-recovery-photo" role="group" aria-label="Исходный снимок и замена">
    <Photo photo={photo} compact onExpand={onExpand} />
    <div className="air-recovery-photo-actions">
      <button className="air-photo-action" aria-label="Камера" onClick={onCamera}><Camera weight="light" /></button>
      <button className="air-photo-action" aria-label="Галерея" onClick={onGallery}><ImageSquare weight="light" /></button>
    </div>
  </div>;
}
function CandidateImage({ candidate, role = "thumbnail", priority = false, size = "64px" }: { candidate: Candidate; role?: "thumbnail" | "card"; priority?: boolean; size?: string }) {
  const [broken, setBroken] = useState(false);
  const variants = (candidate.imageVariants ?? []).filter((variant) => variant.path);
  const preferred = variants.find((variant) => variant.role === role) ?? variants[0];
  const image = preferred?.path ?? candidate.image;
  const srcSet = variants.length > 1 ? [...variants].sort((a, b) => b.width - a.width).filter((variant, index, all) => all.findIndex((item) => item.width === variant.width) === index).sort((a, b) => a.width - b.width).map((variant) => `${variant.path} ${variant.width}w`).join(", ") : undefined;
  useEffect(() => setBroken(false), [image]);
  return image && !broken ? (
    <img
      src={image}
      srcSet={srcSet}
      sizes={role === "card" ? "(min-width: 1024px) 230px, 52vw" : size}
      width={preferred?.width}
      height={preferred?.height}
      loading={priority ? "eager" : "lazy"}
      alt={`Фото вина: ${candidate.name}`}
      onError={() => setBroken(true)}
    />
  ) : (
    <div
      className="missing-image"
      role="img"
      aria-label={`Фото ${candidate.name} недоступно`}
    >
      <ImageSquare />
      <span>
        Фото
        <br />
        отсутствует
      </span>
    </div>
  );
}
function WineList({
  wines,
  onChoose,
  leader = false,
  className = "",
}: {
  wines: Candidate[];
  onChoose: (wine: Candidate) => void;
  leader?: boolean;
  className?: string;
}) {
  return (
    <div className={`candidate-list${leader ? " leader-list" : ""}${className ? ` ${className}` : ""}`}>
      {wines.map((wine, index) => {
        const isLeader = leader && index === 0;
        const year = wine.year && wine.year > 0 ? String(wine.year) : "";
        const color = wine.color?.trim() || "";
        const basicColor = /^(красное|белое|розовое)$/i.test(color) ? color : "";
        const facts = [wine.categoryAndSweetness || [basicColor, wine.sugar].filter(Boolean).join(" "), alcoholLabel(wine)].filter(Boolean);
        return (
        <button
          key={wine.id}
          className={isLeader ? "candidate-leader" : undefined}
          onClick={() => onChoose(wine)}
          aria-label={[wine.name, wine.line, year].filter(Boolean).join(", ")}
        >
            <CandidateImage candidate={wine} priority={index < 4} size={leader ? (isLeader ? "76px" : "56px") : "64px"} />
            <span>
            {isLeader && <em>Наиболее похожее</em>}
            <b>{wine.name}{year && <small className="air-candidate-year"> {year}</small>}</b>
            {wine.line && <small>{wine.line}</small>}
            {wine.winery && <small>{wine.winery}</small>}
            {facts.length > 0 && <small className="air-candidate-meta">{facts.join(" · ")}</small>}
          </span>
          <ArrowRight className="air-candidate-arrow" weight="light" aria-hidden="true" />
        </button>
        );
      })}
    </div>
  );
}
function RecommendationList({
  wines,
  onChoose,
}: {
  wines: Candidate[];
  onChoose: (wine: Candidate) => void;
}) {
  return <WineList wines={wines} onChoose={onChoose} leader className="recommendation-list" />;
}
function BottomNav({
  section,
  onHome,
  onSearch,
  onSaved,
}: {
  section: "scanner" | "search" | "saved";
  onHome: () => void;
  onSearch: () => void;
  onSaved: () => void;
}) {
  return (
    <nav className="bottom-nav" aria-label="Основная навигация" data-section={section}>
      <span className="nav-slider" aria-hidden="true" />
      <button
        aria-current={section === "scanner" ? "page" : undefined}
        onClick={onHome}
      >
        <House weight="light" />
        <span>Главная</span>
      </button>
      <button
        aria-current={section === "search" ? "page" : undefined}
        onClick={onSearch}
      >
        <MagnifyingGlass weight="light" />
        <span>Поиск</span>
      </button>
      <button
        aria-current={section === "saved" ? "page" : undefined}
        onClick={onSaved}
      >
        <BookmarkSimple weight="light" />
        <span>Сохранённое</span>
      </button>
    </nav>
  );
}
function ProductFooter() {
  return (
    <footer className="product-footer">Информация о российских винах</footer>
  );
}
function displayYear(year?: number) {
  return hasYear(year) ? String(year) : "Год не указан";
}
function hasYear(year?: number): year is number {
  return typeof year === "number" && Number.isInteger(year) && year > 0;
}
function safeSourceUrl(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && url.hostname && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}
function isPositiveFinite(value: number | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
function alcoholLabel(wine: Candidate) {
  if (isPositiveFinite(wine.alcoholPercent)) return `${wine.alcoholPercent}%`;
  const min = isPositiveFinite(wine.alcoholMinPercent) ? wine.alcoholMinPercent : undefined;
  const max = isPositiveFinite(wine.alcoholMaxPercent) ? wine.alcoholMaxPercent : undefined;
  if (min !== undefined && max !== undefined) return min <= max ? `${min}–${max}%` : "";
  if (min !== undefined) return `от ${min}%`;
  if (max !== undefined) return `до ${max}%`;
  return "";
}
function isCandidateList(value: unknown): value is Candidate[] {
  return (
    Array.isArray(value) &&
    new Set(
      value.map((item) =>
        item && typeof item === "object" ? (item as Candidate).id : "",
      ),
    ).size === value.length &&
    value.every((item) => {
      if (!item || typeof item !== "object") return false;
      const candidate = item as Record<string, unknown>;
      return (
        ["id", "name", "winery", "image", "description"].every(
          (key) => typeof candidate[key] === "string",
        ) &&
        (candidate.year === undefined ||
          (typeof candidate.year === "number" && Number.isInteger(candidate.year)))
      );
    })
  );
}
