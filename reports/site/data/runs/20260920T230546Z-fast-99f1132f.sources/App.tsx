import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  BookmarkSimple,
  Camera,
  Check,
  ImageSquare,
  MagnifyingGlass,
  X,
} from "@phosphor-icons/react";
import { IconBookmark, IconHome, IconSearch } from "@tabler/icons-react";
import {
  getCatalog,
  getRecommendations,
  InvalidPhotoError,
  searchWine,
  uploadPhoto,
} from "./api";
import type { Candidate, PhotoReceipt, Scenario } from "./types";
import { AtlasScan } from "./AtlasIcons";
import { InstallApp } from "./InstallApp";
import { MascotScene, V2Logo } from "./V2Visual";

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
  const [saved, setSaved] = useState<Candidate[]>([]);
  const [storageNotice, setStorageNotice] = useState("");
  const [selected, setSelected] = useState<Candidate>();
  const [tab, setTab] = useState<"overview" | "description" | "source">(
    "overview",
  );
  const [query, setQuery] = useState("");
  const [permissionDenied] = useState(simulatePermissionDenied);
  const [expandedPhoto, setExpandedPhoto] = useState(false);
  const [lightTip, setLightTip] = useState(false);
  const [candidateOrigin, setCandidateOrigin] =
    useState<CandidateOrigin>("scan");
  const [resultOrigin, setResultOrigin] = useState<ResultOrigin>("scan");
  const [candidateHasPhoto, setCandidateHasPhoto] = useState(false);
  const [resultHasPhoto, setResultHasPhoto] = useState(false);
  const [resultFromCorrection, setResultFromCorrection] = useState(false);
  const [searchOrigin, setSearchOrigin] = useState<SearchOrigin>("normal");
  const [errorKind, setErrorKind] = useState<ErrorKind>("server");
  const [recommendations, setRecommendations] = useState<{
    status: RecommendationStatus;
    candidates: Candidate[];
  }>({ status: "idle", candidates: [] });
  const [recommendationAttempt, setRecommendationAttempt] = useState(0);
  const abort = useRef<AbortController | undefined>(undefined);
  const catalogAbort = useRef<AbortController | undefined>(undefined);
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
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const contentRef = useRef<HTMLDivElement>(null);
  const previousScreen = useRef<Screen>("welcome");
  const searchScroll = useRef(0);
  const listScroll = useRef(0);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const correctionResult = useRef<
    {
      wine: Candidate;
      origin: ResultOrigin;
      hasPhoto: boolean;
      tab: "overview" | "description" | "source";
      section: "scanner" | "search" | "saved";
    } | undefined
  >(undefined);

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = undefined;
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
      recommendationAbort.current?.abort();
      stopCamera();
      if (waitTimer.current) clearTimeout(waitTimer.current);
    },
    [],
  );
  useEffect(
    () => () => {
      if (photo?.startsWith("blob:")) URL.revokeObjectURL(photo);
    },
    [photo],
  );
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    if (screen === "search" && previousScreen.current === "result")
      content.scrollTop = listScroll.current;
    else if (screen === "saved" && previousScreen.current === "result")
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
      setScreen("badphoto");
      return;
    }
    stopCamera();
    setPhotoFile(file);
    setReceipt(undefined);
    setPhoto(URL.createObjectURL(file));
    uploadThenSearch(file, scenario);
  };
  const uploadThenSearch = async (file: File, next: Scenario, q?: string) => {
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
      const list = data.candidates;
      setCandidates(list);
      if (!list.length) {
        setScreen("missing");
        return;
      }
      if (q || next === "uncertain" || !data.selectedId) {
        setCandidateOrigin(
          q
            ? searchOrigin === "correction"
              ? "correction"
              : "manual"
            : "scan",
        );
        setCandidateHasPhoto(Boolean(knownReceipt));
        setScreen("candidates");
        return;
      }
      setSelected(list.find((c) => c.id === data.selectedId) ?? list[0]);
      setResultOrigin("scan");
      setResultHasPhoto(Boolean(knownReceipt));
      setResultFromCorrection(false);
      setTab("overview");
      setScreen("result");
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
          : runSearch(lastRequest.current.scenario, lastRequest.current.query)
      : runSearch(lastRequest.current.scenario, lastRequest.current.query);
  const cancel = () => {
    abort.current?.abort();
    clearWaitTimer();
    setExpandedPhoto(false);
    setSection("scanner");
    setScreen("welcome");
  };
  const openCamera = () =>
    permissionDenied ? setScreen("permission") : setScreen("camera");
  const leaveWork = () => {
    abort.current?.abort();
    catalogAbort.current?.abort();
    if (waitTimer.current) clearTimeout(waitTimer.current);
    stopCamera();
    setExpandedPhoto(false);
  };
  const newCapture = () => {
    leaveWork();
    setSection("scanner");
    setPhoto(undefined);
    setPhotoFile(undefined);
    setReceipt(undefined);
    setSelected(undefined);
    setCandidates([]);
    setCandidateHasPhoto(false);
    setResultHasPhoto(false);
    setResultFromCorrection(false);
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
    setQuery("");
    setCatalogOpen(false);
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
    setSection("scanner");
    setScreen("welcome");
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
    lastRequest.current = { scenario, hasPhoto: false };
  };
  const choose = (c: Candidate) => {
    setSelected(c);
    if (candidateOrigin !== "correction") setResultOrigin(candidateOrigin);
    setResultFromCorrection(candidateOrigin === "correction");
    setResultHasPhoto(candidateHasPhoto);
    setTab("overview");
    setScreen("result");
  };
  const chooseCatalog = (c: Candidate) => {
    listScroll.current = contentRef.current?.scrollTop ?? 0;
    setSelected(c);
    setCandidates([]);
    setResultOrigin("catalog");
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setTab("overview");
    setScreen("result");
  };
  const chooseSaved = (c: Candidate) => {
    listScroll.current = contentRef.current?.scrollTop ?? 0;
    setSelected(c);
    setCandidates([]);
    setResultOrigin("saved");
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setTab("overview");
    setScreen("result");
  };
  const chooseRecommendation = (c: Candidate) => {
    setSelected(c);
    setResultHasPhoto(false);
    setResultFromCorrection(false);
    setTab("overview");
  };
  const rememberCorrection = () => {
    if (selected)
      correctionResult.current = {
        wine: selected,
        origin: resultOrigin,
        hasPhoto: resultHasPhoto,
        tab,
        section,
      };
  };
  const restoreCorrection = () => {
    const snapshot = correctionResult.current;
    if (!snapshot) return false;
    setSelected(snapshot.wine);
    setResultOrigin(snapshot.origin);
    setResultHasPhoto(snapshot.hasPhoto);
    setTab(snapshot.tab);
    setSection(snapshot.section);
    setResultFromCorrection(false);
    setScreen("result");
    return true;
  };
  const openManualCorrection = () => {
    leaveWork();
    setSection("search");
    setSearchOrigin("correction");
    setScreen("search");
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
  const backFromSearch = () => {
    if (searchOrigin === "correction" && restoreCorrection()) return;
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
  const loadCatalog = () => {
    catalogAbort.current?.abort();
    const controller = new AbortController();
    catalogAbort.current = controller;
    setCatalogError("");
    getCatalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && catalogAbort.current === controller)
          setCatalog(data.candidates);
      })
      .catch((error) => {
        if (
          !controller.signal.aborted &&
          catalogAbort.current === controller &&
          (error as Error).name !== "AbortError"
        )
          setCatalogError("Не удалось открыть каталог. Попробуйте ещё раз.");
      });
  };
  useEffect(() => {
    if (
      screen !== "search" ||
      catalog.length ||
      (!catalogOpen && !query.trim())
    )
      return;
    loadCatalog();
    return () => catalogAbort.current?.abort();
  }, [screen, catalog.length, catalogOpen, query]);
  const shown = selected;
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
  const filteredCatalog = catalog.filter((item) =>
    `${item.name} ${item.winery} ${item.year}`
      .toLocaleLowerCase("ru")
      .includes(query.trim().toLocaleLowerCase("ru")),
  );
  const showNav =
    !["camera", "loading", "waiting"].includes(screen) && !expandedPhoto;

  return (
    <main className="app-shell">
      <section className="app" data-testid="app">
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
              {(photo || lastRequest.current.query) && (
                <div className="retained-photo">
                  {photo && (
                    <Photo
                      photo={photo}
                      compact
                      onExpand={() => setExpandedPhoto(true)}
                    />
                  )}
                  <button className="primary" onClick={retry}>
                    Продолжить поиск
                  </button>
                  {photo && (
                    <button
                      className="text-button"
                      onClick={discardRetainedPhoto}
                    >
                      Удалить фото
                    </button>
                  )}
                </div>
              )}
              <div className="actions">
                <button className="primary scan-button" onClick={openCamera}>
                  <Camera />
                  <span>
                    <b>Сканировать вино</b>
                    <small>Наведите на этикетку</small>
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
              <Tip />
              <InstallApp />
              <ProductFooter />
            </Page>
          )}
          {screen === "camera" && (
            <div className="camera-page" id="UI-002">
              <div className="camera-header">
                <Top title="Сканировать этикетку" onBack={back} />
                <p>
                  {lightTip
                    ? "Поверните этикетку так, чтобы убрать блик."
                    : "Наведите на этикетку. Название должно быть читаемым."}
                </p>
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
                <span className="neighbor-hint">Нужная бутылка по центру</span>
              </div>
              <canvas ref={canvasRef} hidden />
              <div className="camera-actions">
                <button
                  className="light-tip"
                  onClick={() => setLightTip((v) => !v)}
                >
                  Подсказка о свете
                </button>
                <button
                  className="shutter"
                  aria-label="Снять фото"
                  onClick={capture}
                >
                  <span />
                </button>
                <button
                  className="text-button"
                  onClick={() => galleryRef.current?.click()}
                >
                  Выбрать фото
                </button>
              </div>
            </div>
          )}
          {screen === "permission" && (
            <Page id="UI-003">
              <Top title="Доступ к камере" onBack={back} />
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
              <button className="primary" onClick={openCamera}>
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
                  ? "Нужно чуть больше времени"
                  : "Узнаём ваше вино"}
              </h2>
              <p>
                {screen === "waiting"
                  ? "Поиск продолжается. Запрос можно отменить."
                  : "Ищем вино по этикетке."}
              </p>
              {photo && lastRequest.current.hasPhoto && (
                <Photo photo={photo} onExpand={() => setExpandedPhoto(true)} />
              )}
              <MascotScene scene="walk" />
              <div className="scan-line" />
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
              <Top title="Похожие вина" onBack={backFromCandidates} />
              <h2>Есть несколько похожих этикеток</h2>
              <p>
                {candidateHasPhoto
                  ? "Сравните название и винодельню со своим снимком."
                  : "Сравните название, винодельню и год."}
              </p>
              {photo && candidateHasPhoto && (
                <Photo
                  photo={photo}
                  compact
                  onExpand={() => setExpandedPhoto(true)}
                />
              )}
              <WineList wines={candidates} onChoose={choose} />
              <button className="secondary" onClick={openManualCorrection}>
                Ни одно не подходит
              </button>
              <button className="text-button" onClick={newCapture}>
                Переснять этикетку
              </button>
            </Page>
          )}
          {screen === "result" &&
            shown &&
            (() => {
              const isSaved = saved.some((item) => item.id === shown.id);
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
                    <CandidateImage candidate={shown} />
                    <div>
                      <span className="demo-label">
                        <Check />
                        Карточка вина
                      </span>
                      <small>{shown.winery}</small>
                      <h2>{shown.name}</h2>
                      <p>{shown.year}</p>
                    </div>
                  </div>
                  {storageNotice && (
                    <p className="storage-notice" role="status">
                      {storageNotice}
                    </p>
                  )}
                  <button
                    className="correction"
                    onClick={() => {
                      rememberCorrection();
                      if (
                        candidates.length &&
                        resultOrigin !== "catalog" &&
                        resultOrigin !== "saved"
                      ) {
                        setCandidateOrigin("correction");
                        setCandidateHasPhoto(resultHasPhoto);
                        setScreen("candidates");
                      } else openManualCorrection();
                    }}
                  >
                    Не это вино? Исправить
                  </button>
                  <div className="tabs" role="tablist">
                    {(["overview", "description", "source"] as const).map(
                      (t, i) => (
                        <button
                          key={t}
                          role="tab"
                          aria-selected={tab === t}
                          onClick={() => setTab(t)}
                        >
                          {["Обзор", "Описание", "Источник"][i]}
                        </button>
                      ),
                    )}
                  </div>
                  {tab === "overview" && (
                    <dl>
                      <div>
                        <dt>Винодельня</dt>
                        <dd>{shown.winery}</dd>
                      </div>
                      <div>
                        <dt>Год</dt>
                        <dd>{shown.year}</dd>
                      </div>
                    </dl>
                  )}
                  {tab === "description" && (
                    <div className="tab-copy">
                      <h3>Описание вина</h3>
                      <p>{shown.description}</p>
                    </div>
                  )}
                  {tab === "source" && (
                    <div className="tab-copy">
                      <h3>Источник</h3>
                      <p>
                        Эта карточка создана для прототипа. После подключения
                        каталога здесь будет ссылка на исходную запись.
                      </p>
                      <a
                        href="https://vino-svoe.ru/"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Открыть платформу «Своё Вино»
                      </a>
                    </div>
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
              <h2>Найдём вручную</h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (query.trim()) {
                    searchScroll.current = contentRef.current?.scrollTop ?? 0;
                    runSearch(scenario, query.trim());
                  }
                }}
              >
                <label htmlFor="query">Название вина или винодельня</label>
                <div className="search-field">
                  <input
                    id="query"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Например, Каберне"
                  />
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
                  <MascotScene scene="browse" />
                  <button
                    className="secondary"
                    onClick={() => setCatalogOpen(true)}
                  >
                    Открыть каталог
                  </button>
                </div>
              )}
              {(query || catalogOpen) &&
                (catalogError ? (
                  <div className="catalog-error" role="alert">
                    <p>{catalogError}</p>
                    <button className="secondary" onClick={loadCatalog}>
                      Повторить
                    </button>
                  </div>
                ) : catalog.length === 0 ? (
                  <p role="status">Загружаем каталог</p>
                ) : filteredCatalog.length ? (
                  <WineList wines={filteredCatalog} onChoose={chooseCatalog} />
                ) : (
                  <p className="empty-catalog">
                    По этому запросу ничего не найдено.
                  </p>
                ))}
              <button className="text-button" onClick={newCapture}>
                Сканировать этикетку
              </button>
              <ProductFooter />
            </Page>
          )}
          {screen === "saved" && (
            <Page id="UI-016">
              <header className="saved-heading">
                <h2>Сохранённые вина</h2>
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
                  <BookmarkSimple />
                  <h3>Пока ничего не сохранено</h3>
                  <p>Откройте карточку вина и нажмите «Сохранить вино».</p>
                  <button className="primary" onClick={openSearch}>
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
                  setSection("search");
                  setScreen("search");
                }}
              />
              <h2>Вино не найдено</h2>
              <p>Подходящего совпадения не нашлось.</p>
              <MascotScene scene="counter" />
              {lastRequest.current.hasPhoto ? (
                <div className="missing-actions">
                  <button className="primary" onClick={openSearch}>
                    Найти по названию
                  </button>
                  <button className="secondary" onClick={newCapture}>
                    Переснять этикетку
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
              <StateIcon>
                <X />
              </StateIcon>
              <h2>
                {errorKind === "network"
                  ? "Нет подключения"
                  : "Сервис временно недоступен"}
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
                <Photo
                  photo={photo}
                  compact
                  onExpand={() => setExpandedPhoto(true)}
                />
              )}
              <MascotScene scene="offline" />
              <button className="primary" onClick={retry}>
                Повторить запрос
              </button>
              {photo && lastRequest.current.hasPhoto && (
                <button className="secondary" onClick={newCapture}>
                  Сделать новый снимок
                </button>
              )}
            </Page>
          )}
          {screen === "badphoto" && (
            <Page id="UI-011">
              <Top title="Неподходящий файл" onBack={back} />
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
    <div className="page" id={id}>
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
function Tip() {
  return (
    <div className="tip welcome-tip">
      <strong>Этикетка целиком, нужная бутылка по центру.</strong>
    </div>
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
function CandidateImage({ candidate }: { candidate: Candidate }) {
  return candidate.image ? (
    <img
      src={candidate.image}
      alt={`Демонстрационное изображение: ${candidate.name}`}
    />
  ) : (
    <div
      className="missing-image"
      role="img"
      aria-label={`Фото ${candidate.name} отсутствует`}
    >
      <ImageSquare />
      <span>
        Демо-фото
        <br />
        отсутствует
      </span>
    </div>
  );
}
function WineList({
  wines,
  onChoose,
}: {
  wines: Candidate[];
  onChoose: (wine: Candidate) => void;
}) {
  return (
    <div className="candidate-list">
      {wines.map((wine) => (
        <button key={wine.id} onClick={() => onChoose(wine)}>
          <CandidateImage candidate={wine} />
          <span>
            <small>{wine.winery}</small>
            <b>{wine.name}</b>
            <small>{wine.year}</small>
          </span>
        </button>
      ))}
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
  return (
    <div className="recommendation-list">
      {wines.map((wine) => (
        <button key={wine.id} onClick={() => onChoose(wine)}>
          <CandidateImage candidate={wine} />
          <span>
            <small>{wine.winery}</small>
            <b>{wine.name}</b>
            <small>{wine.year}</small>
          </span>
        </button>
      ))}
    </div>
  );
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
    <nav className="bottom-nav" aria-label="Основная навигация">
      <button
        aria-current={section === "scanner" ? "page" : undefined}
        onClick={onHome}
      >
        <IconHome />
        <span>Главная</span>
      </button>
      <button
        aria-current={section === "search" ? "page" : undefined}
        onClick={onSearch}
      >
        <IconSearch />
        <span>Поиск</span>
      </button>
      <button
        aria-current={section === "saved" ? "page" : undefined}
        onClick={onSaved}
      >
        <IconBookmark />
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
        typeof candidate.year === "number" &&
        Number.isInteger(candidate.year)
      );
    })
  );
}
