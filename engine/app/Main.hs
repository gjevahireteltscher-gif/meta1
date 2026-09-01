module Main where

import Control.Monad (unless)
import Data.List (find, isPrefixOf, nubBy, sortOn)
import Metonymy.Automatic
import Metonymy.Contextual
import Metonymy.ContextualChecked
import Metonymy.ContextSpec
import Metonymy.Data
import Metonymy.Examples
import Metonymy.GF
import Metonymy.Forgetting
import Metonymy.Ontology
  ( EntityInfo
  , KnowledgeBase (..)
  , entityGF
  , entityId
  )
import Metonymy.Resolution
import Metonymy.Snapshot
import Metonymy.OpenDomain
import Metonymy.Promotion
import Metonymy.Types
import Metonymy.Verified
import System.Environment (getArgs)
import System.Exit (die)

pgfPath :: FilePath
pgfPath = "GeneratedMetonymy.pgf"

main :: IO ()
main = do
  arguments <- getArgs
  let contextualSnapshotPath = requestedSnapshotPath arguments
      contextualScenarioPath = requestedScenarioPath arguments
      formalFilteringEnabled = "--no-formal-filtering" `notElem` arguments
      commandArguments = stripContextualOptions arguments
  rows <- loadAuthorWorkRows "data/wikidata-author-works.tsv"
  localPredicates <- loadPredicates "data/predicates.tsv"
  verbNetPredicates <- loadPredicates "data/verbnet-predicates.tsv"
  verbNetActionRoles <-
    loadActionRoleRequirements "data/verbnet-action-roles.tsv"
  semanticEntities <- loadSemanticEntityRows "data/semantic-entities.tsv"
  semanticRelations <- loadSemanticRelationRows "data/semantic-relations.tsv"
  subsorts <- loadSubsortRows "data/subsorts.tsv"
  endpointSnapshot <- loadEndpointSnapshot "data/entity-link-snapshot.tsv"
  (qidSnapshot, _) <- loadSnapshot contextualSnapshotPath
  contextualScenarios <-
    loadContextScenarios qidSnapshot contextualScenarioPath
  let knowledgeBase =
        extendWithSemanticData
          (extendWithAuthorWorks exampleKnowledgeBase rows)
          semanticEntities
          semanticRelations
          subsorts
      predicates = localPredicates <> verbNetPredicates
      actionRoles = buildActionRoleIndex predicates verbNetActionRoles
  case commandArguments of
    ["list"] -> listScenarios knowledgeBase
    ["expand", input] ->
      case findScenarioIn knowledgeBase input of
        Just _ -> runExpand knowledgeBase predicates input
        Nothing -> runExpandText knowledgeBase predicates [] input
    [ "expand"
      , sentence
      , "--discourse-salient"
      , target
      , "--evidence-source"
      , source
      ] -> do
        evidence <- requireEvidence knowledgeBase target source
        runExpandText knowledgeBase predicates [evidence] sentence
    ["contract", sentence] ->
      runContractText knowledgeBase predicates [] sentence
    [ "contract"
      , sentence
      , "--discourse-salient"
      , target
      , "--evidence-source"
      , source
      ] -> do
        evidence <- requireEvidence knowledgeBase target source
        runContractText knowledgeBase predicates [evidence] sentence
    ["contract", scenarioName', targetName] ->
      runContract knowledgeBase predicates scenarioName' (EntityId targetName)
    ["parse", sentence] -> runParse sentence
    ["evaluate", ablation, direction, sentence] ->
      runEvaluation
        knowledgeBase
        predicates
        ablation
        direction
        sentence
    [ "open-evaluate"
      , ablation
      , dataset
      , category
      , target
      , sentence
      ] ->
        runOpenEvaluation
          knowledgeBase
          endpointSnapshot
          actionRoles
          ablation
          dataset
          category
          target
          sentence
    ["open-batch", ablation] ->
      runOpenBatch knowledgeBase endpointSnapshot actionRoles ablation
    ["contextual-fiber", scenarioName] ->
      case find ((== scenarioName) . contextScenarioName) contextualScenarios of
        Just scenario ->
          runContextualFiber formalFilteringEnabled qidSnapshot scenario
        Nothing -> die ("unknown contextual scenario: " <> scenarioName)
    ["contextual-contract", scenarioName, target] ->
      case find ((== scenarioName) . contextScenarioName) contextualScenarios of
        Just scenario ->
          runContextualContraction
            formalFilteringEnabled
            qidSnapshot
            scenario
            (EntityId target)
        Nothing -> die ("unknown contextual scenario: " <> scenarioName)
    _ -> usage

listScenarios :: KnowledgeBase -> IO ()
listScenarios knowledgeBase =
  mapM_
    ( \scenario ->
        putStrLn
          ( scenarioName scenario
              <> "  "
              <> inputTree knowledgeBase scenario
          )
    )
    (scenariosFor knowledgeBase)

runExpand :: KnowledgeBase -> [Predicate] -> String -> IO ()
runExpand knowledgeBase predicates name = do
  scenario <- requireScenario knowledgeBase name
  inputSurface <- requireLinearization (inputTree knowledgeBase scenario)
  putStrLn ("input: " <> inputSurface)
  let candidates =
        reverse
          (sortOn candidateScore (expandScenario knowledgeBase scenario))
  mapM_ (printCandidate knowledgeBase predicates []) candidates

runContract :: KnowledgeBase -> [Predicate] -> String -> EntityId -> IO ()
runContract knowledgeBase predicates name target = do
  scenario <- requireScenario knowledgeBase name
  targetInfo <-
    case filter ((== target) . entityId) (entities knowledgeBase) of
      info : _ -> pure info
      [] -> die ("unknown target entity: " <> show target)
  inputSurface <-
    requireLinearization
      (replaceTargetTree scenario (entityGFName targetInfo))
  putStrLn ("input: " <> inputSurface)
  case contractScenario knowledgeBase scenario target of
    Nothing ->
      die
        "contraction rejected: the target is not the generic, safely forgettable representative"
    Just candidate -> printCandidate knowledgeBase predicates [] candidate

runExpandText ::
  KnowledgeBase ->
  [Predicate] ->
  [DiscourseEvidence] ->
  String ->
  IO ()
runExpandText knowledgeBase predicates evidence sentence = do
  trees <- parseSentenceTrees sentence
  let candidates =
        uniqueCandidates
          (concatMap (automaticExpand knowledgeBase predicates) trees)
  if null candidates
    then
      die
        "no type mismatch with an admissible ontology bridge was found"
    else do
      putStrLn ("input: " <> sentence)
      mapM_
        (printCandidate knowledgeBase predicates evidence)
        (reverse (sortOn candidateScore candidates))

runContractText ::
  KnowledgeBase ->
  [Predicate] ->
  [DiscourseEvidence] ->
  String ->
  IO ()
runContractText knowledgeBase predicates evidence sentence = do
  let forgetContext = inferForgetContext sentence
  unless
    (safeToForget forgetContext)
    ( die
        ( "contraction rejected by contextual safety gate: "
            <> unwords (rejectionCodes forgetContext)
        )
    )
  trees <- parseSentenceTrees sentence
  let candidates =
        map (bindForgetContext forgetContext)
          ( uniqueCandidates
              (concatMap (automaticContract knowledgeBase predicates) trees)
          )
  if null candidates
    then
      die
        "no safely forgettable generic reading with an incoming ontology bridge was found"
    else do
      putStrLn ("input: " <> sentence)
      mapM_ (printCandidate knowledgeBase predicates evidence) candidates

bindForgetContext :: ForgetContext -> Candidate -> Candidate
bindForgetContext context candidate =
  candidate
    { candidateCertificate =
        (candidateCertificate candidate)
          { certificateForgetContext = context
          }
    }

parseSentenceTrees :: String -> IO [String]
parseSentenceTrees sentence = do
  parseResult <-
    parseEnglish
      pgfPath
      ( normalizeInitialArticle
          (stripTerminalPunctuation sentence)
      )
  case parseResult of
    Left message -> die ("GF parse failed: " <> message)
    Right parsedTrees -> pure parsedTrees

stripTerminalPunctuation :: String -> String
stripTerminalPunctuation =
  reverse
    . dropWhile (`elem` (".!?" :: String))
    . reverse

normalizeInitialArticle :: String -> String
normalizeInitialArticle ('T' : 'h' : 'e' : rest) =
  't' : 'h' : 'e' : rest
normalizeInitialArticle sentence =
  sentence

uniqueCandidates :: [Candidate] -> [Candidate]
uniqueCandidates =
  nubBy
    ( \left right ->
        candidateAbstractTree left == candidateAbstractTree right
    )

runContextualFiber :: Bool -> Snapshot -> ContextScenario -> IO ()
runContextualFiber formalFiltering snapshot scenario =
  case towerResult of
    Left message -> die ("contextual fiber failed: " <> message)
    Right stages -> do
      putStrLn ("graph_sha256=" <> snapshotHash snapshot)
      putStrLn
        ( "source="
            <> show (contextSource context)
            <> " action="
            <> contextAction context
            <> " role="
            <> show (contextRole context)
        )
      mapM_ printStage stages
  where
    context = contextScenarioContext scenario
    allowedRelations = contextScenarioRelations scenario
    maxDepth = contextScenarioMaxDepth scenario
    printStage stage = do
      putStrLn
        ( "stage="
            <> show (stageIndex stage)
            <> " constraint="
            <> maybe "graph-related" renderConstraint (stageConstraint stage)
        )
      putStrLn
        ( "  survivors="
            <> show (map (fineTarget . contextualFineMeaning) (stageCandidates stage))
        )
      putStrLn
        ( "  agda-layer-check="
            <> if formalFiltering then "true" else "disabled"
        )
      mapM_ (putStrLn . ("  obstruction=" <>) . show) (stageObstructions stage)
      case stageConstraint stage of
        Just constraint
          | payloadIsPreference (constraintPayload constraint) -> do
              putStrLn
                ( "  preferred="
                    <> show
                      ( map
                          (fineTarget . contextualFineMeaning)
                          (stagePreferredCandidates stage)
                      )
                )
              mapM_
                (putStrLn . ("  preference-miss=" <>) . show)
                (stagePreferenceMisses stage)
        _ -> pure ()

    renderConstraint constraint =
      show (constraintPayload constraint)
        <> "@"
        <> anchorLemma (constraintOrigin constraint)

    towerResult =
      if formalFiltering
        then contextualFiberChecked snapshot allowedRelations maxDepth context
        else contextualFiber snapshot allowedRelations maxDepth context

runContextualContraction ::
  Bool ->
  Snapshot ->
  ContextScenario ->
  EntityId ->
  IO ()
runContextualContraction formalFiltering snapshot scenario target =
  case
      if formalFiltering
        then
          contextualContractionChecked
            snapshot
            (contextScenarioRelations scenario)
            (contextScenarioMaxDepth scenario)
            (contextScenarioContext scenario)
            target
        else
          contextualContractionUnchecked
            snapshot
            (contextScenarioRelations scenario)
            (contextScenarioMaxDepth scenario)
            (contextScenarioContext scenario)
            target of
    Left message ->
      die ("contextual contraction rejected: " <> message)
    Right result -> do
      putStrLn ("graph_sha256=" <> snapshotHash snapshot)
      putStrLn
        ( "contract="
            <> show (contractionTarget result)
            <> " -> "
            <> show (contractionSource result)
            <> " safety="
            <> contractionSafety result
        )
      mapM_ printContractionStage (contractionStages result)
  where
    printContractionStage stage = do
      putStrLn
        ( "stage="
            <> show (stageIndex stage)
            <> " constraint="
            <> maybe "graph-related" renderConstraint (stageConstraint stage)
        )
      putStrLn
        ( "  survivors="
            <> show (stageTargets stage)
        )
      putStrLn
        ( "  agda-layer-check="
            <> if formalFiltering then "true" else "disabled"
        )
      case stageConstraint stage of
        Just constraint
          | payloadIsPreference (constraintPayload constraint) ->
              putStrLn
                ( "  preferred="
                    <> show
                      ( map
                          (fineTarget . contextualFineMeaning)
                          (stagePreferredCandidates stage)
                      )
                )
        _ -> pure ()

    renderConstraint constraint =
      show (constraintPayload constraint)
        <> "@"
        <> anchorLemma (constraintOrigin constraint)

runParse :: String -> IO ()
runParse sentence = do
  result <- parseEnglish pgfPath sentence
  case result of
    Left message -> die message
    Right trees -> mapM_ putStrLn trees

printCandidate ::
  KnowledgeBase ->
  [Predicate] ->
  [DiscourseEvidence] ->
  Candidate ->
  IO ()
printCandidate knowledgeBase predicates evidence candidate = do
  surface <- requireLinearization (candidateAbstractTree candidate)
  let certificate = candidateCertificate candidate
      runtimePrecheck = verifyCertificate knowledgeBase certificate
      agdaAccepted = verifyWithAgda knowledgeBase predicates certificate
      roundTrip = roundTripHolds knowledgeBase certificate
      authorization =
        authorizeCandidate
          knowledgeBase
          predicates
          evidence
          candidate
  unless agdaAccepted $
    die
      ( "trusted Agda checker rejected candidate: "
          <> candidateAbstractTree candidate
      )
  authorized <-
    case authorization of
      Nothing ->
        die
          ( "Agda runtime rewrite checker rejected candidate: "
              <> candidateAbstractTree candidate
          )
      Just accepted -> pure accepted
  putStrLn
    ( "candidate: "
        <> surface
        <> "  score="
        <> show (candidateScore candidate)
    )
  putStrLn ("  tree: " <> candidateAbstractTree candidate)
  putStrLn
    ( "  bridge: "
        <> renderBridgePath (finePath (certificateFine certificate))
    )
  putStrLn
    ( "  constraint: "
        <> show (predicateStrength (certificatePredicate certificate))
        <> " source="
        <> predicateProvenance (certificatePredicate certificate)
    )
  putStrLn
    ( "  status="
        <> authorizationStatus authorized
        <> " path="
        <> show (authorizationHasPath authorized)
    )
  putStrLn
    ( "  certificate="
        <> ( case predicateStrength (certificatePredicate certificate) of
              HardRequirement -> "agda-verified-path"
              SelectionalPreference -> "agda-verified-preference"
           )
        <> " runtime-precheck="
        <> show runtimePrecheck
        <> " round-trip="
        <> show roundTrip
    )

authorizationStatus :: Authorization -> String
authorizationStatus DirectHardPath =
  "hard-requirement"
authorizationStatus PreferenceCandidate =
  "candidate-only"
authorizationStatus (PromotedPreferencePath evidence) =
  "promoted-preference evidence="
    <> show (evidenceTarget evidence)
    <> "@"
    <> evidenceSource evidence

authorizationHasPath :: Authorization -> Bool
authorizationHasPath DirectHardPath =
  True
authorizationHasPath PreferenceCandidate =
  False
authorizationHasPath (PromotedPreferencePath _) =
  True

requireEvidence ::
  KnowledgeBase ->
  String ->
  String ->
  IO DiscourseEvidence
requireEvidence knowledgeBase target source
  | null source =
      die "evidence source must not be empty"
  | otherwise =
      case filter ((== EntityId target) . entityId) (entities knowledgeBase) of
        _ : _ ->
          pure
            TargetSalient
              { evidenceTarget = EntityId target
              , evidenceSource = source
              }
        [] ->
          die ("unknown evidence target entity: " <> target)

runEvaluation ::
  KnowledgeBase ->
  [Predicate] ->
  String ->
  String ->
  String ->
  IO ()
runEvaluation knowledgeBase predicates ablation direction sentence = do
  unless
    (ablation `elem` ["full", "no-types", "no-ontology", "no-context", "no-verbnet"])
    (die ("unknown evaluation ablation: " <> ablation))
  let (ablatedKnowledgeBase, ablatedPredicates) =
        applyAblation ablation knowledgeBase predicates
  case direction of
    "expand" ->
      runExpandText
        ablatedKnowledgeBase
        ablatedPredicates
        []
        sentence
    "contract" ->
      runContractText
        ablatedKnowledgeBase
        ablatedPredicates
        []
        sentence
    _ -> die ("unknown evaluation direction: " <> direction)

applyAblation ::
  String ->
  KnowledgeBase ->
  [Predicate] ->
  (KnowledgeBase, [Predicate])
applyAblation "full" knowledgeBase predicates =
  (knowledgeBase, predicates)
applyAblation "no-types" knowledgeBase predicates =
  ( knowledgeBase
      { typeAssertions = []
      , subsortRules = []
      }
  , predicates
  )
applyAblation "no-ontology" knowledgeBase predicates =
  (knowledgeBase {relationAssertions = []}, predicates)
applyAblation "no-context" knowledgeBase predicates =
  (knowledgeBase, predicates)
applyAblation "no-verbnet" knowledgeBase predicates =
  ( knowledgeBase
  , filter
      (not . isPrefixOf "VerbNet-" . predicateProvenance)
      predicates
  )
applyAblation unknown _ _ =
  error ("unknown evaluation ablation: " <> unknown)

runOpenEvaluation ::
  KnowledgeBase ->
  [EndpointProposal] ->
  ActionRoleIndex ->
  String ->
  String ->
  String ->
  String ->
  String ->
  IO ()
runOpenEvaluation
  base endpointSnapshot actionRoles ablation dataset category target sentence = do
  unless
    (ablation `elem` ["full", "no-types", "no-ontology", "no-context", "no-verbnet"])
    (die ("unknown evaluation ablation: " <> ablation))
  let result =
        evaluateOpen
          endpointSnapshot
          actionRoles
          base
          ablation
          (datasetHint dataset category)
          target
          Nothing
          sentence
  mapM_ putStrLn (renderOpenResult result)

data OpenEvaluationResult
  = OpenEvaluationLiteral
  | OpenEvaluationAbstain String
  | OpenEvaluationRejected OpenFamily
  | OpenEvaluationPreference OpenFamily Candidate
  | OpenEvaluationAuthorized OpenFamily Candidate

evaluateOpen ::
  [EndpointProposal] ->
  ActionRoleIndex ->
  KnowledgeBase ->
  String ->
  DatasetHint ->
  String ->
  Maybe (Int, Int) ->
  String ->
  OpenEvaluationResult
evaluateOpen
  endpointSnapshot actionRoles base ablation hint target targetSpan sentence =
  resolveOpenDecision
    ablation
    ( analyzeOpenAtWithEndpoints
        endpointSnapshot actionRoles base hint target targetSpan sentence
    )

-- | Same authorization pipeline as 'evaluateOpen', but for a candidate
-- proposed by the UD dependency-parser frontend
-- ('analyzeOpenAtWithDependencyHint') instead of the legacy positional
-- heuristic. Sharing 'resolveOpenDecision' keeps ablation handling and
-- certificate authorization byte-identical between the two frontends, so
-- 'renderOpenBatchRow' output remains directly comparable.
evaluateOpenWithDependencyHint ::
  [EndpointProposal] ->
  ActionRoleIndex ->
  KnowledgeBase ->
  String ->
  DatasetHint ->
  String ->
  Maybe (Int, Int) ->
  DependencyHint ->
  String ->
  OpenEvaluationResult
evaluateOpenWithDependencyHint
  endpointSnapshot actionRoles base ablation hint target targetSpan dep sentence =
  resolveOpenDecision
    ablation
    ( analyzeOpenAtWithDependencyHint
        endpointSnapshot actionRoles base hint target targetSpan dep sentence
    )

resolveOpenDecision :: String -> OpenDecision -> OpenEvaluationResult
resolveOpenDecision ablation decision =
  case decision of
    OpenLiteral ->
      OpenEvaluationLiteral
    OpenAbstain reason ->
      OpenEvaluationAbstain reason
    OpenRewrite family candidateKnowledgeBase candidatePredicates candidate ->
      let (ablatedKnowledgeBase, ablatedPredicates) =
            applyAblation
              ablation
              candidateKnowledgeBase
              candidatePredicates
       in case
          authorizeCandidate
            ablatedKnowledgeBase
            ablatedPredicates
            []
            candidate
        of
        Just DirectHardPath ->
          OpenEvaluationAuthorized family candidate
        Just PreferenceCandidate ->
          OpenEvaluationPreference family candidate
        _ ->
          OpenEvaluationRejected family

-- | Parse the three trailing dependency-hint TSV columns
-- (@hole_role@, @governing_lemma@, @dep_status@) produced by
-- @scripts/annotate_dependency_hints.py@.
parseDependencyHint :: String -> String -> String -> Either String DependencyHint
parseDependencyHint holeRoleField lemmaField statusField = do
  status <- case statusField of
    "direct-argument" -> Right DirectArgument
    "nested-modifier" -> Right NestedModifier
    "no-governing-verb" -> Right NoGoverningVerb
    "parse-error" -> Right ParseError
    other -> Left ("open-batch: unknown dep_status " <> other)
  hole <- case holeRoleField of
    "Subject" -> Right (Just SubjectHole)
    "Object" -> Right (Just ObjectHole)
    "" -> Right Nothing
    other -> Left ("open-batch: unknown hole_role " <> other)
  let lemma = if null lemmaField then Nothing else Just lemmaField
  Right (DependencyHint status hole lemma)

renderOpenResult :: OpenEvaluationResult -> [String]
renderOpenResult OpenEvaluationLiteral =
  ["status=no-rewrite prediction=literal frontend=open-gf"]
renderOpenResult (OpenEvaluationAbstain reason) =
  ["status=abstain frontend=open-gf reason=" <> reason]
renderOpenResult (OpenEvaluationRejected family) =
  [ "status=rejected frontend=open-gf family="
      <> openFamilyName family
  ]
renderOpenResult (OpenEvaluationPreference family candidate) =
  [ "status=abstain frontend=open-gf reason=selectional-preference-needs-evidence family="
      <> openFamilyName family
  , "candidate-endpoint=" <> candidateSurface candidate
  ]
renderOpenResult (OpenEvaluationAuthorized family candidate) =
  [ "status=authorized prediction=metonymic frontend=open-gf family="
      <> openFamilyName family
  , "source-tree=" <> candidateSourceTree candidate
  , "target-tree=" <> candidateAbstractTree candidate
  , "endpoint=" <> candidateSurface candidate
  ]

datasetHint :: String -> String -> DatasetHint
datasetHint "wimcor" _ =
  WiMCorLocation
datasetHint "conmec" category =
  ConMeCCategory category
datasetHint _ _ =
  UnspecifiedDomain

runOpenBatch ::
  KnowledgeBase ->
  [EndpointProposal] ->
  ActionRoleIndex ->
  String ->
  IO ()
runOpenBatch base endpointSnapshot actionRoles ablation = do
  unless
    (ablation `elem` ["full", "no-types", "no-ontology", "no-context", "no-verbnet"])
    (die ("unknown evaluation ablation: " <> ablation))
  contents <- getContents
  mapM_ processLine (filter (not . null) (lines contents))
  where
    processLine line =
      case splitTabs line of
        [identifier, dataset, category, target, sentence] ->
          putStrLn
            ( renderOpenBatchRow
                identifier
                ( evaluateOpen
                    endpointSnapshot
                    actionRoles
                    base
                    ablation
                    (datasetHint dataset category)
                    target
                    Nothing
                    sentence
                )
            )
        [identifier, dataset, category, target, start, end, sentence] ->
          case (reads start, reads end) of
            ([(startOffset, "")], [(endOffset, "")]) ->
              putStrLn
                ( renderOpenBatchRow
                    identifier
                    ( evaluateOpen
                        endpointSnapshot
                        actionRoles
                        base
                        ablation
                        (datasetHint dataset category)
                        target
                        (Just (startOffset, endOffset))
                        sentence
                    )
                )
            _ -> die "open-batch target offsets must be integers"
        [ identifier, dataset, category, target, start, end, sentence
          , holeRoleField, lemmaField, statusField
          ] ->
          case (reads start, reads end) of
            ([(startOffset, "")], [(endOffset, "")]) ->
              case parseDependencyHint holeRoleField lemmaField statusField of
                Left message -> die message
                Right dep ->
                  putStrLn
                    ( renderOpenBatchRow
                        identifier
                        ( evaluateOpenWithDependencyHint
                            endpointSnapshot
                            actionRoles
                            base
                            ablation
                            (datasetHint dataset category)
                            target
                            (Just (startOffset, endOffset))
                            dep
                            sentence
                        )
                    )
            _ -> die "open-batch target offsets must be integers"
        _ ->
          die
            ( "open-batch expects id,dataset,category,target,[start,end,]"
                <> "sentence[,hole_role,governing_lemma,dep_status] TSV"
            )

splitTabs :: String -> [String]
splitTabs value =
  case break (== '\t') value of
    (field, []) -> [field]
    (field, _ : rest) -> field : splitTabs rest

renderOpenBatchRow :: String -> OpenEvaluationResult -> String
renderOpenBatchRow identifier OpenEvaluationLiteral =
  identifier <> "\tno_rewrite\tliteral\t\t"
renderOpenBatchRow identifier (OpenEvaluationAbstain reason) =
  identifier <> "\tabstain\t\t\t" <> reason
renderOpenBatchRow identifier (OpenEvaluationRejected family) =
  identifier
    <> "\trejected\t\t"
    <> openFamilyName family
    <> "\tformal-rejection"
renderOpenBatchRow identifier (OpenEvaluationPreference family candidate) =
  identifier
    <> "\tabstain\t\t"
    <> openFamilyName family
    <> "\tselectional-preference:"
    <> candidateSurface candidate
renderOpenBatchRow identifier (OpenEvaluationAuthorized family candidate) =
  identifier
    <> "\temitted\tmetonymic\t"
    <> openFamilyName family
    <> "\t"
    <> candidateSurface candidate

requireScenario :: KnowledgeBase -> String -> IO Scenario
requireScenario knowledgeBase name =
  case findScenarioIn knowledgeBase name of
    Just scenario -> pure scenario
    Nothing -> die ("unknown scenario: " <> name)

requireLinearization :: String -> IO String
requireLinearization tree = do
  result <- linearize pgfPath tree
  case result of
    Left message -> die ("GF linearization failed: " <> message)
    Right surface -> pure surface

entityGFName :: EntityInfo -> String
entityGFName = entityGF

replaceTargetTree :: Scenario -> String -> String
replaceTargetTree scenario targetGF =
  case scenarioHoleRole scenario of
    SubjectHole ->
      "Pred "
        <> targetGF
        <> " (Compl "
        <> gfFunction (scenarioPredicate scenario)
        <> " "
        <> scenarioOtherArgumentGF scenario
        <> ")"
    ObjectHole ->
      "Pred "
        <> scenarioOtherArgumentGF scenario
        <> " (Compl "
        <> gfFunction (scenarioPredicate scenario)
        <> " "
        <> targetGF
        <> ")"

usage :: IO a
usage =
  die
    ( unlines
        [ "usage:"
        , "  metonymy list"
        , "  metonymy expand \"English sentence\""
        , "    [--discourse-salient ENTITY-ID --evidence-source SOURCE]"
        , "  metonymy contract \"English sentence\""
        , "    [--discourse-salient ENTITY-ID --evidence-source SOURCE]"
        , "  metonymy expand SCENARIO"
        , "  metonymy contract SCENARIO TARGET-ID"
        , "  metonymy parse \"English sentence\""
        , "  metonymy evaluate ABLATION expand|contract \"English sentence\""
        , "  metonymy open-evaluate ABLATION DATASET CATEGORY TARGET \"English sentence\""
        , "  metonymy open-batch ABLATION  # TSV on stdin"
        , "    id,dataset,category,target,[start,end,]sentence  (legacy frontend)"
        , "    id,dataset,category,target,start,end,sentence,"
        , "      hole_role,governing_lemma,dep_status  (UD dependency-hint frontend)"
        , "  metonymy contextual-fiber SCENARIO"
        , "    [--snapshot PATH] [--scenarios PATH]"
        , "  metonymy contextual-contract SCENARIO TARGET-QID"
        , "    [--snapshot PATH] [--scenarios PATH]"
        ]
    )

requestedSnapshotPath :: [String] -> FilePath
requestedSnapshotPath = optionValue "--snapshot" "data/wikidata-qid-snapshot"

requestedScenarioPath :: [String] -> FilePath
requestedScenarioPath = optionValue "--scenarios" "data/contextual-scenarios.tsv"

optionValue :: String -> String -> [String] -> String
optionValue _ fallback [] = fallback
optionValue option fallback (name : value : rest)
  | name == option = value
  | otherwise = optionValue option fallback (value : rest)
optionValue _ fallback [_] = fallback

stripContextualOptions :: [String] -> [String]
stripContextualOptions [] = []
stripContextualOptions (name : _ : rest)
  | name `elem` ["--snapshot", "--scenarios"] =
      stripContextualOptions rest
stripContextualOptions (value : rest) =
  if value == "--no-formal-filtering"
    then stripContextualOptions rest
    else value : stripContextualOptions rest
