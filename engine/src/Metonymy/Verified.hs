module Metonymy.Verified
  ( verifyWithAgda
  , verifyRuntimeWithAgda
  , verifyPreferenceRuntimeWithAgda
  , verifyContextualRuntimeWithAgda
  , verifyContextLayerWithAgda
  , verifyPreferenceLayerWithAgda
  , verifyPromotionWithAgda
  ) where

import qualified Data.Text as Text
import qualified Metonymy.CheckerAPI as Agda
import Metonymy.Automatic (Clause (..), parseClause)
import Metonymy.Contextual
import Metonymy.Ontology
import Metonymy.Types

verifyWithAgda ::
  KnowledgeBase ->
  [Predicate] ->
  Certificate ->
  Bool
verifyWithAgda knowledgeBase predicates certificate =
  Agda.check
    (toAgdaKnowledgeBase knowledgeBase predicates)
    (toAgdaCertificate selectedRequirement certificate)
  where
    predicate = certificatePredicate certificate
    selectedRequirement =
      case certificateHoleRole certificate of
        SubjectHole -> subjectRequirement predicate
        ObjectHole -> objectRequirement predicate

verifyRuntimeWithAgda ::
  KnowledgeBase ->
  [Predicate] ->
  Candidate ->
  Bool
verifyRuntimeWithAgda knowledgeBase predicates candidate =
  verifyRuntimeCandidate
    Agda.runtimeCheck
    knowledgeBase
    predicates
    candidate

verifyPreferenceRuntimeWithAgda ::
  KnowledgeBase ->
  [Predicate] ->
  Candidate ->
  Bool
verifyPreferenceRuntimeWithAgda knowledgeBase predicates candidate =
  verifyRuntimeCandidate
    Agda.preferenceRuntimeCheck
    knowledgeBase
    predicates
    candidate

verifyContextualRuntimeWithAgda ::
  Snapshot ->
  [Predicate] ->
  Context ->
  Candidate ->
  Bool
verifyContextualRuntimeWithAgda snapshot predicates context candidate =
  case
      ( parseClause (candidateSourceTree candidate)
      , parseClause (candidateAbstractTree candidate)
      ) of
    (Just before, Just after) ->
      Agda.contextualRuntimeCheck
        (toAgdaKnowledgeBase knowledgeBase predicates)
        (toAgdaClause (certificateForgetContext certificate) before)
        (toAgdaClause (certificateForgetContext certificate) after)
        (toAgdaCertificate selectedRequirement certificate)
        (text (snapshotHash snapshot))
        (toAgdaContext context)
    _ -> False
  where
    knowledgeBase = snapshotKnowledgeBase snapshot
    certificate = candidateCertificate candidate
    predicate = certificatePredicate certificate
    selectedRequirement =
      case certificateHoleRole certificate of
        SubjectHole -> subjectRequirement predicate
        ObjectHole -> objectRequirement predicate

verifyContextLayerWithAgda :: Snapshot -> Context -> EntityId -> Bool
verifyContextLayerWithAgda snapshot context candidate =
  Agda.contextLayerCheck
    (toAgdaKnowledgeBase (snapshotKnowledgeBase snapshot) [])
    (text (snapshotHash snapshot))
    (toAgdaContext context)
    (text (show candidate))

verifyPreferenceLayerWithAgda ::
  Snapshot ->
  ContextConstraint ->
  EntityId ->
  Bool
verifyPreferenceLayerWithAgda snapshot constraint candidate =
  Agda.contextPreferenceCheck
    (toAgdaKnowledgeBase (snapshotKnowledgeBase snapshot) [])
    (toAgdaContextConstraint constraint)
    (text (show candidate))

toAgdaContext :: Context -> Agda.RawContext
toAgdaContext context =
  Agda.rawContext
    (text (contextSnapshotHash context))
    (text (contextAction context))
    (map toAgdaContextConstraint (contextConstraints context))
    (map text (contextRuleProvenance context))

toAgdaContextConstraint :: ContextConstraint -> Agda.RawContextConstraint
toAgdaContextConstraint constraint =
  Agda.rawContextConstraint
    (toAgdaAnchor (constraintOrigin constraint))
    (case constraintPayload constraint of
      Requires requirement -> Agda.rawRequires (toAgdaRequirement requirement)
      RequiresRelation relation target ->
        Agda.rawRequiresRelation (text (show relation)) (text (show target))
      RequiresSome relation requirement ->
        Agda.rawRequiresSome
          (text (show relation))
          (toAgdaRequirement requirement)
      Prefers requirement ->
        Agda.rawPrefers (toAgdaRequirement requirement)
      PrefersRelation relation target ->
        Agda.rawPrefersRelation
          (text (show relation))
          (text (show target))
      PrefersSome relation requirement ->
        Agda.rawPrefersSome
          (text (show relation))
          (toAgdaRequirement requirement)
    )
    (text (constraintProvenance constraint))

toAgdaAnchor :: LexicalAnchor -> Agda.RawLexicalAnchor
toAgdaAnchor anchor =
  Agda.rawLexicalAnchor
    (text (anchorGFConstructor anchor))
    (text (anchorLemma anchor))
    (text (anchorSurface anchor))
    (fromIntegral (anchorStart anchor))
    (fromIntegral (anchorEnd anchor))

verifyRuntimeCandidate ::
  ( Agda.KnowledgeBase ->
    Agda.RuntimeClause ->
    Agda.RuntimeClause ->
    Agda.RawCertificate ->
    Bool
  ) ->
  KnowledgeBase ->
  [Predicate] ->
  Candidate ->
  Bool
verifyRuntimeCandidate checker knowledgeBase predicates candidate =
  case
      ( parseClause (candidateSourceTree candidate)
      , parseClause (candidateAbstractTree candidate)
      ) of
    (Just before, Just after) ->
      checker
        (toAgdaKnowledgeBase knowledgeBase predicates)
        (toAgdaClause (certificateForgetContext certificate) before)
        (toAgdaClause (certificateForgetContext certificate) after)
        (toAgdaCertificate selectedRequirement certificate)
    _ -> False
  where
    certificate = candidateCertificate candidate
    predicate = certificatePredicate certificate
    selectedRequirement =
      case certificateHoleRole certificate of
        SubjectHole -> subjectRequirement predicate
        ObjectHole -> objectRequirement predicate

verifyPromotionWithAgda ::
  Certificate ->
  DiscourseEvidence ->
  Bool
verifyPromotionWithAgda certificate evidence =
  Agda.checkPromotion
    (toAgdaCertificate selectedRequirement certificate)
    (Just (toAgdaEvidence evidence))
  where
    predicate = certificatePredicate certificate
    selectedRequirement =
      case certificateHoleRole certificate of
        SubjectHole -> subjectRequirement predicate
        ObjectHole -> objectRequirement predicate

toAgdaKnowledgeBase ::
  KnowledgeBase ->
  [Predicate] ->
  Agda.KnowledgeBase
toAgdaKnowledgeBase knowledgeBase predicates =
  Agda.knowledgeBase
    (map toTypeFact (typeAssertions knowledgeBase))
    (map toRelationFact (relationAssertions knowledgeBase))
    (map toSubsortRule (subsortRules knowledgeBase))
    (map toPredicateFact predicates)
    (map toLexemeFact (entities knowledgeBase))

toLexemeFact :: EntityInfo -> Agda.LexemeFact
toLexemeFact info =
  Agda.lexemeFact
    (text (entityGF info))
    (text (show (entityId info)))

toAgdaClause :: ForgetContext -> Clause -> Agda.RuntimeClause
toAgdaClause context clause =
  Agda.runtimeClause
    (text (clauseSubjectGF clause))
    (text (clauseVerbGF clause))
    (text (clauseObjectGF clause))
    (toAgdaForgetContext context)

toAgdaForgetContext :: ForgetContext -> Agda.ForgetContext
toAgdaForgetContext context =
  Agda.forgetContext
    (genericWholeFiber context)
    (hasRestrictor context)
    (hasQuantifier context)
    (isPositive context)
    (isUnfocused context)
    (hasAnaphoricDependent context)
    (hasTemporalRestriction context)

toAgdaEvidence ::
  DiscourseEvidence ->
  Agda.RawDiscourseEvidence
toAgdaEvidence evidence =
  Agda.targetSalient
    (text (show (evidenceTarget evidence)))
    (text (evidenceSource evidence))

toTypeFact :: TypeAssertion -> Agda.TypeFact
toTypeFact assertion =
  Agda.typeFact
    (text (show (typedEntity assertion)))
    (text (show (assertedSort assertion)))

toRelationFact :: RelationAssertion -> Agda.RelationFact
toRelationFact assertion =
  Agda.relationFact
    (text (show (assertedRelation assertion)))
    (text (show (relationSource assertion)))
    (text (show (relationTarget assertion)))

toSubsortRule :: (Sort, Sort, String) -> Agda.SubsortRule
toSubsortRule (subsort, supersort, _) =
  Agda.subsortRule
    (text (show subsort))
    (text (show supersort))

toPredicateFact :: Predicate -> Agda.PredicateFact
toPredicateFact predicate =
  Agda.predicateFact
    (text (gfFunction predicate))
    (toAgdaRequirement (subjectRequirement predicate))
    (toAgdaRequirement (objectRequirement predicate))
    (text (show (predicateStrength predicate)))
    (text (predicateProvenance predicate))

toAgdaCertificate ::
  Requirement ->
  Certificate ->
  Agda.RawCertificate
toAgdaCertificate requirement certificate =
  Agda.rawCertificate
    (toDirection (certificateDirection certificate))
    (toAgdaForgetContext (certificateForgetContext certificate))
    (text (gfFunction predicate))
    (toHole (certificateHoleRole certificate))
    (text (show (coarseSource (certificateCoarse certificate))))
    (text (show (fineTarget fine)))
    (toAgdaRequirement requirement)
    (text (show (predicateStrength predicate)))
    (text (predicateProvenance predicate))
    (map toEdge (unBridgePath (finePath fine)))
  where
    predicate = certificatePredicate certificate
    fine = certificateFine certificate

toDirection :: Direction -> Agda.Direction
toDirection Expand = Agda.expand
toDirection Contract = Agda.contract

toHole :: HoleRole -> Agda.Hole
toHole SubjectHole = Agda.subjectHole
toHole ObjectHole = Agda.objectHole

toEdge :: BridgeStep -> Agda.Edge
toEdge step =
  Agda.edge
    (text (show (bridgeRelation step)))
    (text (show (bridgeSource step)))
    (text (show (bridgeTarget step)))

toAgdaRequirement :: Requirement -> Agda.Requirement
toAgdaRequirement (HasSort sort) = Agda.hasSort (text (show sort))
toAgdaRequirement (AllOf requirements) =
  Agda.allOf (map toAgdaRequirement requirements)
toAgdaRequirement (AnyOf requirements) =
  Agda.anyOf (map toAgdaRequirement requirements)
toAgdaRequirement (Not requirement) =
  Agda.notRequirement (toAgdaRequirement requirement)

text :: String -> Text.Text
text = Text.pack
