module Main where

import Control.Monad (unless)
import Data.List (find, isPrefixOf)
import Metonymy.Automatic
import Metonymy.Contextual
import Metonymy.ContextualChecked
import Metonymy.ContextSpec
import Metonymy.Data
import Metonymy.Elaborator
import Metonymy.Examples
import Metonymy.GF
import Metonymy.Forgetting
import Metonymy.Ontology (KnowledgeBase)
import Metonymy.OpenDomain
import Metonymy.Promotion
import Metonymy.Resolution
import Metonymy.Snapshot
import Metonymy.Types
import Metonymy.Verified
import Metonymy.Waterloo
import System.Exit (exitFailure)

main :: IO ()
main = do
  importedRows <- loadAuthorWorkRows "data/wikidata-author-works.tsv"
  localPredicates <- loadPredicates "data/predicates.tsv"
  verbNetPredicates <- loadPredicates "data/verbnet-predicates.tsv"
  verbNetActionRoles <-
    loadActionRoleRequirements "data/verbnet-action-roles.tsv"
  endpointSnapshot <- loadEndpointSnapshot "data/entity-link-snapshot.tsv"
  (waterlooSnapshot, waterlooRules) <-
    loadSnapshot "data/wikidata-qid-snapshot"
  waterlooAliases <- loadSnapshotAliases "data/wikidata-qid-snapshot"
  loadedContextScenarios <-
    loadContextScenarios waterlooSnapshot "data/contextual-scenarios.tsv"
  semanticEntities <- loadSemanticEntityRows "data/semantic-entities.tsv"
  semanticRelations <- loadSemanticRelationRows "data/semantic-relations.tsv"
  subsorts <- loadSubsortRows "data/subsorts.tsv"
  let expandedKnowledgeBase =
        extendWithSemanticData
          (extendWithAuthorWorks exampleKnowledgeBase importedRows)
          semanticEntities
          semanticRelations
          subsorts
      predicates = localPredicates <> verbNetPredicates
      openActionRoles =
        buildActionRoleIndex predicates verbNetActionRoles
      waterlooContext = waterlooContextFor waterlooSnapshot

  readScenario <- require "read-tolstoy"
  glassScenario <- require "drink-glass"
  moscowScenario <- require "moscow-signs"

  let readCandidates = expandScenario exampleKnowledgeBase readScenario
      glassCandidates = expandScenario exampleKnowledgeBase glassScenario
      moscowCandidates = expandScenario exampleKnowledgeBase moscowScenario

  assert "read expansion has generic and specific works" (length readCandidates == 3)
  assert "glass expansion has one content" (length glassCandidates == 1)
  assert "Moscow expansion has one institution" (length moscowCandidates == 1)

  assert
    "every expansion certificate verifies"
    ( all
        (verifyCertificate exampleKnowledgeBase . candidateCertificate)
        (readCandidates <> glassCandidates <> moscowCandidates)
    )

  assert
    "every expansion certificate has the round-trip property"
    ( all
        (roundTripHolds exampleKnowledgeBase . candidateCertificate)
        (readCandidates <> glassCandidates <> moscowCandidates)
    )

  assert
    "generic author contraction is permitted"
    ( contractScenario
        exampleKnowledgeBase
        readScenario
        (EntityId "works-of-tolstoy")
        /= Nothing
    )

  assert
    "specific work contraction is rejected as lossy"
    ( contractScenario
        exampleKnowledgeBase
        readScenario
        (EntityId "war-and-peace")
        == Nothing
    )

  assertLinearizes
    "the expanded subject is linearized"
    "Pred RussianGovernment (Compl Sign Agreement)"
    "the Russian government signs the agreement"

  assertLinearizes
    "open proper names linearize through the GF English RGL"
    "Pred (OpenPN \"London\") (Compl OpenAgentive OpenContextNP)"
    "London represents context"

  assertLinearizes
    "open common nouns preserve determiner and agreement"
    "Pred (OpenIndefCN \"bottle\" \"bottles\") (Compl OpenConsumptive OpenContextNP)"
    "a bottle contains context"

  assertLinearizes
    "GF preserves explicit negative polarity in the contextual tree"
    "NegPred Anna (Compl Read Tolstoy)"
    "Anna doesn't read Tolstoy"

  assertLinearizes
    "GF preserves quantification in the contextual tree"
    "Pred (EveryCN \"student\" \"students\") (Compl Read Tolstoy)"
    "every student reads Tolstoy"

  assertLinearizes
    "GF preserves PP modification in the contextual tree"
    "Pred (ModifyNP Moscow (InPP RussianGovernment)) (Compl Sign Agreement)"
    "Moscow in the Russian government signs the agreement"

  assertParses
    "GF parses the metonymic reading example"
    "Anna reads Tolstoy"

  assertParses
    "GF parses the explicit author-work expansion"
    "Anna reads Tolstoy's works"

  assertParses
    "GF parses the container-content example"
    "Anna drinks the contents of a glass"

  assertParses
    "GF parses the place-institution expansion"
    "the Russian government signs the agreement"

  assertRecognizes
    "free-text recognition finds the metonymic author source"
    "Anna reads Tolstoy"
    "read-tolstoy"
    (EntityId "tolstoy")

  assertRecognizes
    "free-text recognition finds the generic author expansion"
    "Anna reads Tolstoy's works"
    "read-tolstoy"
    (EntityId "works-of-tolstoy")

  assertRecognizes
    "free-text recognition finds a subject metonymy"
    "Moscow signs the agreement"
    "moscow-signs"
    (EntityId "moscow")

  assert "Wikidata snapshot contains 92 typed facts" (length importedRows == 92)
  assert "VerbNet snapshot contributes 41 predicates" (length verbNetPredicates == 41)
  assert
    "all VerbNet constraints remain marked as preferences"
    ( all
        ((== SelectionalPreference) . predicateStrength)
        verbNetPredicates
    )
  assert
    "Wikidata snapshot generates 33 additional author scenarios"
    (length (scenariosFor expandedKnowledgeBase) == length scenarios + 33)

  let importedScenarios =
        filter
          (isPrefixOf "read-Q" . scenarioName)
          (scenariosFor expandedKnowledgeBase)
      importedCandidates =
        concatMap (expandScenario expandedKnowledgeBase) importedScenarios
      namedCandidates =
        [ (scenario, candidate)
        | scenario <- importedScenarios
        , candidate <- expandScenario expandedKnowledgeBase scenario
        , fineTarget
            (certificateFine (candidateCertificate candidate))
            /= scenarioGenericTarget scenario
        ]

  assert
    "all 33 imported author scenarios are available"
    (length importedScenarios == 33)
  assert
    "imported fibers contain 33 generic and 92 named meanings"
    (length importedCandidates == 125)
  assert
    "all 125 imported certificates verify and round-trip"
    ( all
        ( \candidate ->
            let certificate = candidateCertificate candidate
             in verifyCertificate expandedKnowledgeBase certificate
                  && roundTripHolds expandedKnowledgeBase certificate
        )
        importedCandidates
    )
  assert
    "every imported generic class contracts safely"
    ( all
        ( \scenario ->
            contractScenario
              expandedKnowledgeBase
              scenario
              (scenarioGenericTarget scenario)
              /= Nothing
        )
        importedScenarios
    )
  assert
    "all 92 imported named works reject lossy contraction"
    ( all
        ( \(scenario, candidate) ->
            contractScenario
              expandedKnowledgeBase
              scenario
              (fineTarget (certificateFine (candidateCertificate candidate)))
              == Nothing
        )
        namedCandidates
    )

  rumiScenario <-
    case findScenarioIn expandedKnowledgeBase "read-Q43347" of
      Just scenario -> pure scenario
      Nothing -> do
        putStrLn "FAIL: generated Rumi scenario is missing"
        exitFailure

  let rumiCandidates = expandScenario expandedKnowledgeBase rumiScenario
  assert
    "Rumi expansion contains a generic class and four named works"
    (length rumiCandidates == 5)
  assert
    "imported Wikidata certificates verify"
    ( all
        (verifyCertificate expandedKnowledgeBase . candidateCertificate)
        rumiCandidates
    )
  assert
    "compiled Agda checker accepts imported Wikidata certificates"
    ( all
        ( verifyWithAgda
            expandedKnowledgeBase
            predicates
            . candidateCertificate
        )
        rumiCandidates
    )
  assert
    "runtime checker binds certificates to their GF source and target trees"
    (all (verifyRuntimeWithAgda expandedKnowledgeBase predicates) rumiCandidates)
  assert
    "runtime checker rejects a certificate attached to a different GF source"
    ( not
        ( verifyRuntimeWithAgda
            expandedKnowledgeBase
            predicates
            ( (head rumiCandidates)
                { candidateSourceTree =
                    "Pred John (Compl Read Works_Q43347)"
                }
            )
        )
    )

  let contextualRumiSnapshot = Snapshot "contextual-rumi-test-v1" expandedKnowledgeBase
      contextualRumiAnchor =
        LexicalAnchor "V2" "read" "reads" 5 10
      contextualRumiContext =
        Context
          { contextTree =
              LexicalApply
                "Pred"
                [ LexicalLeaf
                    contextualRumiAnchor
                    [Requires (HasSort Readable)]
                ]
          , contextSnapshotHash = snapshotHash contextualRumiSnapshot
          , contextSource = EntityId "Q43347"
          , contextAction = "read"
          , contextRole = ObjectHole
          , contextConstraints =
              [ ContextConstraint
                  contextualRumiAnchor
                  (Requires (HasSort Readable))
                  "test:readable"
              ]
          , contextRuleProvenance = ["test:readable"]
          }
      contextualRumiCandidate = head rumiCandidates
  assert
    "compiled Agda contextual checker accepts matching hash, action, origin, and constraint"
    ( verifyContextualRuntimeWithAgda
        contextualRumiSnapshot
        predicates
        contextualRumiContext
        contextualRumiCandidate
    )
  assert
    "compiled Agda contextual checker rejects a mismatched snapshot hash"
    ( not
        ( verifyContextualRuntimeWithAgda
            contextualRumiSnapshot
            predicates
            (contextualRumiContext {contextSnapshotHash = "forged-snapshot"})
            contextualRumiCandidate
        )
    )
  let invalidSpanAnchor =
        contextualRumiAnchor {anchorEnd = anchorStart contextualRumiAnchor}
      invalidSpanContext =
        contextualRumiContext
          { contextTree =
              LexicalLeaf invalidSpanAnchor [Requires (HasSort Readable)]
          , contextConstraints =
              [ ContextConstraint invalidSpanAnchor (Requires (HasSort Readable)) "test:readable"
              ]
          }
  assert
    "compiled Agda contextual checker rejects an invalid lexical span"
    ( not
        ( verifyContextualRuntimeWithAgda
            contextualRumiSnapshot
            predicates
            invalidSpanContext
            contextualRumiCandidate
        )
    )
  let missingProvenanceContext =
        contextualRumiContext
          { contextConstraints =
              [ ContextConstraint
                  contextualRumiAnchor
                  (Requires (HasSort Readable))
                  ""
              ]
          }
  assert
    "compiled Agda contextual checker rejects missing composition provenance"
    ( not
        ( verifyContextualRuntimeWithAgda
            contextualRumiSnapshot
            predicates
            missingProvenanceContext
            contextualRumiCandidate
        )
    )
  let forgedProvenanceContext =
        contextualRumiContext
          { contextConstraints =
              [ ContextConstraint
                  contextualRumiAnchor
                  (Requires (HasSort Readable))
                  "forged-rule"
              ]
          }
  assert
    "compiled Agda contextual checker rejects provenance absent from rule snapshot"
    ( not
        ( verifyContextualRuntimeWithAgda
            contextualRumiSnapshot
            predicates
            forgedProvenanceContext
            contextualRumiCandidate
        )
    )

  let validCertificate = candidateCertificate (head rumiCandidates)
      validFine = certificateFine validCertificate
      validPredicate = certificatePredicate validCertificate
      validSteps = unBridgePath (finePath validFine)
      forgedTarget =
        validCertificate
          { certificateFine =
              validFine {fineTarget = EntityId "forged-target"}
          }
      forgedRequirement =
        validCertificate
          { certificatePredicate =
              validPredicate
                { objectRequirement = HasSort Edible
                }
          }
      forgedProvenance =
        validCertificate
          { certificatePredicate =
              validPredicate
                { predicateProvenance = "forged:provenance"
                }
          }
      emptyPath =
        validCertificate
          { certificateFine =
              validFine {finePath = BridgePath []}
          }
      forgedRelation =
        case validSteps of
          step : rest ->
            validCertificate
              { certificateFine =
                  validFine
                    { finePath =
                        BridgePath
                          (step {bridgeRelation = Contains} : rest)
                    }
              }
          [] -> validCertificate

  assert
    "Agda checker rejects a forged target"
    (not (verifyWithAgda expandedKnowledgeBase predicates forgedTarget))
  assert
    "Agda checker rejects a forged predicate requirement"
    (not (verifyWithAgda expandedKnowledgeBase predicates forgedRequirement))
  assert
    "Agda checker rejects forged provenance"
    (not (verifyWithAgda expandedKnowledgeBase predicates forgedProvenance))
  assert
    "Agda checker rejects an empty path"
    (not (verifyWithAgda expandedKnowledgeBase predicates emptyPath))
  assert
    "Agda checker rejects a forged relation"
    (not (verifyWithAgda expandedKnowledgeBase predicates forgedRelation))

  assertRecognizesWith
    expandedKnowledgeBase
    "generated lexicon parses and recognizes Rumi"
    "Anna reads Rumi"
    "read-Q43347"
    (EntityId "Q43347")

  assertRecognizesWith
    expandedKnowledgeBase
    "compositional recognition accepts a different reader"
    "John reads Rumi"
    "read-Q43347"
    (EntityId "Q43347")

  assertRecognizesWith
    expandedKnowledgeBase
    "generated lexicon recognizes a named Rumi work"
    "Anna reads Masnavi"
    "read-Q43347"
    (EntityId "Q6579646")

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "study reuses the author-work bridge by target type"
    "John studies Rumi"
    5

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "review works without a dedicated metonymy scenario"
    "Mary reviews Arthur Schnitzler"
    6

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "listen to selects audible works"
    "Alice listens to Mozart"
    2

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "watch selects films through creator relations"
    "Bob watches Spielberg"
    2

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "eat selects edible container contents"
    "John eats a plate"
    1

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "wear selects products of a brand"
    "Mary wears Chanel"
    1

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "selectional mismatch without a compatible bridge is rejected"
    "John drinks Rumi"
    0

  assertAutomaticContraction
    expandedKnowledgeBase
    predicates
    "generic audible work contracts through the same relation"
    "Alice listens to Mozart's music"
    1

  assertAutomaticContraction
    expandedKnowledgeBase
    predicates
    "specific named works remain unsafe to contract"
    "Alice listens to Eine kleine Nachtmusik"
    0

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet scrutiny preference activates readable works"
    "John scrutinizes Rumi"
    5

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet auditory preference activates musical works"
    "Alice hears Mozart"
    2

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet visual preference activates films"
    "Bob views Spielberg"
    2

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet ingestion preference activates edible contents"
    "John devours a plate"
    1

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet garment preference activates brand products"
    "Mary dons Chanel"
    1

  assertAutomaticExpansion
    expandedKnowledgeBase
    predicates
    "VerbNet liquid preference activates container contents"
    "Alice sips a glass"
    1

  assertAutomaticContraction
    expandedKnowledgeBase
    predicates
    "VerbNet-imported predicates support reverse resolution"
    "John scrutinizes Rumi's works"
    1

  scrutinyTrees <- requireParsedTrees "John scrutinizes Rumi"
  let scrutinyCandidates =
        concatMap
          (automaticExpand expandedKnowledgeBase predicates)
          scrutinyTrees
      noEvidenceAuthorizations =
        map
          (authorizeCandidate expandedKnowledgeBase predicates [])
          scrutinyCandidates
      salience =
        TargetSalient
          { evidenceTarget = EntityId "works-of-Q43347"
          , evidenceSource = "conversation:turn-4"
          }
      promotedAuthorizations =
        zip
          scrutinyCandidates
          ( map
              (authorizeCandidate expandedKnowledgeBase predicates [salience])
              scrutinyCandidates
          )
      promoted =
        [ candidate
        | (candidate, Just (PromotedPreferencePath _)) <-
            promotedAuthorizations
        ]
  assert
    "preferences remain candidate-only without discourse evidence"
    ( all
        (== Just PreferenceCandidate)
        noEvidenceAuthorizations
    )
  assert
    "matching discourse salience promotes exactly the generic Rumi reading"
    ( case promoted of
        [candidate] ->
          fineTarget
            (certificateFine (candidateCertificate candidate))
            == EntityId "works-of-Q43347"
        _ -> False
    )
  assert
    "empty evidence provenance cannot promote a preference"
    ( case find
        ( (== EntityId "works-of-Q43347")
            . fineTarget
            . certificateFine
            . candidateCertificate
        )
        scrutinyCandidates of
        Nothing -> False
        Just candidate ->
          authorizeCandidate
            expandedKnowledgeBase
            predicates
            [TargetSalient (EntityId "works-of-Q43347") ""]
            candidate
            == Just PreferenceCandidate
    )

  case
      analyzeOpen
        openActionRoles
        expandedKnowledgeBase
        WiMCorLocation
        "Moscow"
        "Moscow signed the agreement"
    of
    OpenRewrite family openKB openPredicateSet candidate -> do
      assert
        "open GF elaboration selects a location-institution bridge"
        (family == LocationInstitution)
      assert
        "open GF candidate is authorized only through the Agda runtime checker"
        ( authorizeCandidate openKB openPredicateSet [] candidate
            == Just DirectHardPath
        )
      assert
        "open GF certificate remains bound to its generated source tree"
        ( authorizeCandidate
            openKB
            openPredicateSet
            []
            (candidate {candidateSourceTree = "Pred Forged (Compl Forged Context)"})
            == Nothing
        )
    _ -> assert "open GF elaboration emits an authorized candidate" False

  case
      analyzeOpenAtWithEndpoints
        endpointSnapshot
        openActionRoles
        expandedKnowledgeBase
        WiMCorLocation
        "Waterloo"
        (Just (0, 8))
        "Waterloo announced a new research programme"
    of
    OpenRewrite family openKB openPredicateSet candidate -> do
      assert
        "VerbNet Action×Role fiber selects an institution-compatible path"
        (family == LocationInstitution)
      assert
        "structured AnyOf role requirement is checked by Agda"
        (verifyPreferenceRuntimeWithAgda openKB openPredicateSet candidate)
    _ ->
      assert
        "VerbNet Action×Role fiber produces a checked preference candidate"
        False

  assert
    "open GF frontend reports a literal use when no bridge trigger is present"
    ( analyzeOpen
        openActionRoles
        expandedKnowledgeBase
        WiMCorLocation
        "Paris"
        "Paris is a city in France"
        == OpenLiteral
    )
  assert
    "open GF frontend abstains when the marked target is absent"
    ( case
        analyzeOpen
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Paris"
          "London signed the agreement"
        of
        OpenAbstain "target-not-found" -> True
        _ -> False
    )
  assert
    "target-aware frontend rejects a forged target span"
    ( case
        analyzeOpenAt
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Moscow"
          (Just (7, 13))
          "Moscow signed the agreement"
        of
        OpenAbstain "invalid-target-span" -> True
        _ -> False
    )
  assert
    "target-aware frontend binds a valid marked occurrence"
    ( case
        analyzeOpenAt
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Moscow"
          (Just (0, 6))
          "Moscow signed the agreement"
        of
        OpenRewrite {} -> True
        _ -> False
    )
  assert
    "dependency frontend: direct-argument subject resolves through the same Action\215Role search"
    ( case
        analyzeOpenAtWithDependencyHint
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Moscow"
          Nothing
          (DependencyHint DirectArgument (Just SubjectHole) (Just "sign"))
          "Moscow signed the agreement"
        of
        OpenRewrite family _ _ _ -> family == LocationInstitution
        _ -> False
    )
  assert
    "dependency frontend: direct-argument object resolves the author-to-works bridge"
    ( case
        analyzeOpenAtWithDependencyHint
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Tolstoy"
          Nothing
          (DependencyHint DirectArgument (Just ObjectHole) (Just "read"))
          "Anna read Tolstoy"
        of
        OpenRewrite {} -> True
        _ -> False
    )
  assert
    "dependency frontend: reconstructed phrasal-verb lemma matches the predicates.tsv key"
    ( case
        analyzeOpenAtWithDependencyHint
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Mozart"
          Nothing
          (DependencyHint DirectArgument (Just ObjectHole) (Just "listen to"))
          "The teenager listened to Mozart"
        of
        OpenRewrite {} -> True
        _ -> False
    )
  let nestedModifierSentence = "Anna reads Tolstoy's books"
      nestedModifierResult =
        analyzeOpenAtWithDependencyHint
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Tolstoy"
          Nothing
          (DependencyHint NestedModifier Nothing Nothing)
          nestedModifierSentence
      legacyOnSameSentence =
        analyzeOpenAtWithEndpoints
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Tolstoy"
          Nothing
          nestedModifierSentence
  assert
    "dependency frontend abstains explicitly on a nested-modifier target"
    (nestedModifierResult == OpenAbstain "nested-modifier-unsupported")
  assert
    "the nested-modifier abstention is a real behavior change, not incidental to the legacy result"
    (legacyOnSameSentence /= nestedModifierResult)
  assert
    "dependency frontend degrades exactly to the legacy frontend on a parser failure"
    ( analyzeOpenAtWithDependencyHint
        endpointSnapshot
        openActionRoles
        expandedKnowledgeBase
        WiMCorLocation
        "Moscow"
        Nothing
        (DependencyHint ParseError Nothing Nothing)
        "Moscow signed the agreement"
        == analyzeOpenAtWithEndpoints
             endpointSnapshot
             openActionRoles
             expandedKnowledgeBase
             WiMCorLocation
             "Moscow"
             Nothing
             "Moscow signed the agreement"
    )
  assert
    "span validation still takes precedence over a nested-modifier dependency hint"
    ( case
        analyzeOpenAtWithDependencyHint
          endpointSnapshot
          openActionRoles
          expandedKnowledgeBase
          WiMCorLocation
          "Moscow"
          (Just (7, 13))
          (DependencyHint NestedModifier Nothing Nothing)
          "Moscow signed the agreement"
        of
        OpenAbstain "invalid-target-span" -> True
        _ -> False
    )

  assert
    "context gate permits unrestricted generic readings"
    (safeToForget (inferForgetContext "Anna reads Tolstoy's works"))
  assert
    "context gate rejects quantifier-sensitive contraction"
    (not (safeToForget (inferForgetContext "Anna reads every work by Tolstoy")))
  assert
    "context gate rejects restrictive and temporal contraction"
    (not (safeToForget (inferForgetContext "Anna reads Tolstoy's early works from 1920")))

  assert
    "Waterloo tree elaborates with ordered lexical origins"
    ( case
        elaborateContext
          (snapshotHash waterlooSnapshot)
          (contextSource waterlooContext)
          "announce"
          SubjectHole
          waterlooTree of
        Right context ->
          map
            (\constraint -> (constraintOrigin constraint, constraintPayload constraint))
            (contextConstraints context)
            == map
              (\constraint -> (constraintOrigin constraint, constraintPayload constraint))
              (contextConstraints waterlooContext)
        Left _ -> False
    )
  assert
    "unsupported lexical construction fails closed"
    ( case
        elaborateContext
          (snapshotHash waterlooSnapshot)
          (contextSource waterlooContext)
          "announce"
          SubjectHole
          (LexicalApply "UnsupportedGFNode" []) of
        Left (UnsupportedConstruction _) -> True
        _ -> False
    )
  assert
    "GF application tree is lexicalized with concrete source spans"
    ( case
        lexicalizeGFTree
          "Waterloo announced programme"
          [ LexicalBinding "WaterlooGF" "waterloo" "Waterloo" []
          , LexicalBinding
              "AnnounceGF"
              "announce"
              "announced"
              [Requires (AnyOf [HasSort Animate, HasSort Organization])]
          , LexicalBinding "ProgrammeGF" "programme" "programme" []
          ]
          "Pred WaterlooGF (Compl AnnounceGF ProgrammeGF)" of
        Right tree ->
          case
              elaborateContext
                (snapshotHash waterlooSnapshot)
                (EntityId "Q639408")
                "announce"
                SubjectHole
                tree of
            Right context ->
              map
                (anchorStart . constraintOrigin)
                (contextConstraints context)
                == [9]
            Left _ -> False
        Left _ -> False
    )
  assert
    "GF quantified lexical constructor retains its noun and span"
    ( case
        lexicalizeGFTree
          "every student reads Tolstoy"
          [ LexicalBinding
              "EveryCN"
              "student"
              "student"
              [Requires (HasSort Human)]
          , LexicalBinding "Read" "read" "reads" []
          , LexicalBinding "Tolstoy" "tolstoy" "Tolstoy" []
          ]
          "Pred (EveryCN \"student\" \"students\") (Compl Read Tolstoy)" of
        Right tree ->
          case
              elaborateContext
                (snapshotHash waterlooSnapshot)
                (EntityId "Q639408")
                "read"
                SubjectHole
                tree of
            Right context ->
              case contextConstraints context of
                [constraint] ->
                  anchorStart (constraintOrigin constraint) == 6
                    && anchorSurface (constraintOrigin constraint) == "student"
                _ -> False
            Left _ -> False
        Left _ -> False
    )
  assert
    "snapshot rules include inverse institution projection"
    ( any
        ( \projection ->
            projectionRelation projection == InstitutionOf
              && projectionInverse projection
        )
        (relationProjections waterlooRules)
    )
  assert
    "snapshot alias layer resolves Waterloo to its QID"
    (lookup "Waterloo" waterlooAliases == Just (EntityId "Q639408"))
  assert
    "Waterloo contextual scenario is loaded from versioned data"
    ( case loadedContextScenarios of
        [scenario] ->
          contextScenarioName scenario == "waterloo"
            && contextSource (contextScenarioContext scenario) == contextSource waterlooContext
            && contextAction (contextScenarioContext scenario) == contextAction waterlooContext
            && contextConstraints (contextScenarioContext scenario) == contextConstraints waterlooContext
        _ -> False
    )
  assert
    "tower rejects a context bound to another snapshot"
    ( contextualFiber
        waterlooSnapshot
        [InstitutionOf]
        1
        (waterlooContext {contextSnapshotHash = "forged"})
        == Left "snapshot-hash-mismatch"
    )

  case
      contextualFiber
        waterlooSnapshot
        [InstitutionOf]
        1
        waterlooContext of
    Left errorMessage -> do
      putStrLn ("FAIL: Waterloo contextual fiber: " <> errorMessage)
      exitFailure
    Right stages -> do
      assert "Waterloo fiber has one initial and two lexical stages" (length stages == 3)
      assert
        "Waterloo graph layer preserves all institution candidates"
        ( stageTargets (stages !! 0)
            == map EntityId ["Q1049470", "Q2004561", "Q7974219"]
        )
      assert
        "announce layer retains organization candidates"
        (stageTargets (stages !! 1) == stageTargets (stages !! 0))
      assert
        "physics layer retains only positively witnessed institutions"
        (stageTargets (stages !! 2) == map EntityId ["Q1049470", "Q2004561"])
      assert
        "contextual fiber is monotonically restricted"
        ( all
            (`elem` stageTargets (stages !! 0))
            (stageTargets (stages !! 1))
            && all
              (`elem` stageTargets (stages !! 1))
              (stageTargets (stages !! 2))
        )
      assert
        "Waterloo council has a precise missing-relation obstruction"
        ( case stageObstructions (stages !! 2) of
            [MissingRelation _ candidate Conducts target] ->
              candidate == EntityId "Q7974219" && target == EntityId "Q413"
            _ -> False
        )

  case
      contextualFiberChecked
        waterlooSnapshot
        [InstitutionOf]
        1
        waterlooContext of
    Left errorMessage -> do
      putStrLn ("FAIL: Agda-checked Waterloo fiber: " <> errorMessage)
      exitFailure
    Right stages ->
      assert
        "Agda-checked Waterloo fiber matches the executable tower"
        (stageTargets (stages !! 2) == map EntityId ["Q1049470", "Q2004561"])

  case
      contextualContractionChecked
        waterlooSnapshot
        [InstitutionOf]
        1
        waterlooContext
        (EntityId "Q1049470") of
    Left "unsafe-contextual-contraction-non-singleton-fiber" ->
      assert "ambiguous Waterloo contraction is rejected" True
    other -> do
      putStrLn ("FAIL: expected unsafe Waterloo contraction, got " <> show other)
      exitFailure

  case
      contextualContractionChecked
        waterlooSnapshot
        [InstitutionOf]
        1
        waterlooContext
        (EntityId "Q7974219") of
    Left "explicit-target-not-in-final-fiber" ->
      assert "obstructed Waterloo council cannot contract" True
    other -> do
      putStrLn ("FAIL: expected missing council contraction, got " <> show other)
      exitFailure

  let uniqueWaterlooContext =
        waterlooContext
          { contextConstraints =
              contextConstraints waterlooContext
                <> [ ContextConstraint
                      (LexicalAnchor "Noun" "university" "university" 46 56)
                      (Requires (HasSort University))
                      "test:unique-university"
                   ]
          , contextRuleProvenance =
              contextRuleProvenance waterlooContext
                <> ["test:unique-university"]
          }
  case
      contextualContractionChecked
        waterlooSnapshot
        [InstitutionOf]
        1
        uniqueWaterlooContext
        (EntityId "Q1049470") of
    Right result ->
      assert
        "unique Waterloo university fiber contracts to the source place"
        ( contractionSource result == EntityId "Q639408"
            && contractionTarget result == EntityId "Q1049470"
            && contractionSafety result == "unique-contextual-fiber"
        )
    Left errorMessage -> do
      putStrLn ("FAIL: unique Waterloo contraction: " <> errorMessage)
      exitFailure

  putStrLn "all tests passed"

require :: String -> IO Scenario
require name =
  case findScenario name of
    Just scenario -> pure scenario
    Nothing -> do
      putStrLn ("missing scenario: " <> name)
      exitFailure

assert :: String -> Bool -> IO ()
assert label condition =
  unless condition $ do
    putStrLn ("FAIL: " <> label)
    exitFailure

assertLinearizes :: String -> String -> String -> IO ()
assertLinearizes label tree expected = do
  result <- linearize "GeneratedMetonymy.pgf" tree
  case result of
    Right actual -> assert label (actual == expected)
    Left message -> do
      putStrLn ("FAIL: " <> label <> ": " <> message)
      exitFailure

assertParses :: String -> String -> IO ()
assertParses label sentence = do
  result <- parseEnglish "GeneratedMetonymy.pgf" sentence
  case result of
    Right trees -> assert label (not (null trees))
    Left message -> do
      putStrLn ("FAIL: " <> label <> ": " <> message)
      exitFailure

requireParsedTrees :: String -> IO [String]
requireParsedTrees sentence = do
  result <- parseEnglish "GeneratedMetonymy.pgf" sentence
  case result of
    Right trees -> pure trees
    Left message -> do
      putStrLn ("FAIL: parse fixture: " <> message)
      exitFailure

assertRecognizes ::
  String ->
  String ->
  String ->
  EntityId ->
  IO ()
assertRecognizes label sentence expectedScenario expectedTarget = do
  assertRecognizesWith
    exampleKnowledgeBase
    label
    sentence
    expectedScenario
    expectedTarget

assertRecognizesWith ::
  KnowledgeBase ->
  String ->
  String ->
  String ->
  EntityId ->
  IO ()
assertRecognizesWith knowledgeBase label sentence expectedScenario expectedTarget = do
  result <- parseEnglish "GeneratedMetonymy.pgf" sentence
  case result of
    Left message -> do
      putStrLn ("FAIL: " <> label <> ": " <> message)
      exitFailure
    Right trees ->
      case
        [ recognition
        | tree <- trees
        , Just recognition <- [recognizeTree knowledgeBase tree]
        ]
      of
        recognition : _ ->
          assert
            label
            ( scenarioName (recognizedScenario recognition)
                == expectedScenario
                && recognizedTarget recognition == expectedTarget
            )
        [] -> do
          putStrLn ("FAIL: " <> label <> ": no recognized parse")
          exitFailure

assertAutomaticExpansion ::
  KnowledgeBase ->
  [Predicate] ->
  String ->
  String ->
  Int ->
  IO ()
assertAutomaticExpansion knowledgeBase predicates label sentence expectedCount = do
  trees <- requireParseTrees label sentence
  let candidates =
        concatMap (automaticExpand knowledgeBase predicates) trees
  assert label (length candidates == expectedCount)
  assert
    (label <> " certificates")
    ( all
        ( \candidate ->
            let certificate = candidateCertificate candidate
             in verifyCertificate knowledgeBase certificate
                  && roundTripHolds knowledgeBase certificate
                  && verifyWithAgda knowledgeBase predicates certificate
        )
        candidates
    )

assertAutomaticContraction ::
  KnowledgeBase ->
  [Predicate] ->
  String ->
  String ->
  Int ->
  IO ()
assertAutomaticContraction knowledgeBase predicates label sentence expectedCount = do
  trees <- requireParseTrees label sentence
  let candidates =
        concatMap (automaticContract knowledgeBase predicates) trees
  assert label (length candidates == expectedCount)
  assert
    (label <> " certificates")
    ( all
        ( \candidate ->
            let certificate = candidateCertificate candidate
             in verifyCertificate knowledgeBase certificate
                  && verifyWithAgda knowledgeBase predicates certificate
        )
        candidates
    )

requireParseTrees :: String -> String -> IO [String]
requireParseTrees label sentence = do
  result <- parseEnglish "GeneratedMetonymy.pgf" sentence
  case result of
    Right trees -> pure trees
    Left message -> do
      putStrLn ("FAIL: " <> label <> ": " <> message)
      exitFailure
