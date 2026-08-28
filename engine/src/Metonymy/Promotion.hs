module Metonymy.Promotion
  ( authorizeCandidate
  ) where

import Data.List (find)
import Metonymy.Ontology (KnowledgeBase)
import Metonymy.Types
import Metonymy.Verified

authorizeCandidate ::
  KnowledgeBase ->
  [Predicate] ->
  [DiscourseEvidence] ->
  Candidate ->
  Maybe Authorization
authorizeCandidate knowledgeBase predicates evidence candidate =
  case predicateStrength predicate of
    HardRequirement ->
      if verifyRuntimeWithAgda knowledgeBase predicates candidate
        then Just DirectHardPath
        else Nothing
    SelectionalPreference ->
      if not (verifyPreferenceRuntimeWithAgda knowledgeBase predicates candidate)
        then Nothing
        else
          case find (verifyPromotionWithAgda certificate) evidence of
            Just acceptedEvidence ->
              Just (PromotedPreferencePath acceptedEvidence)
            Nothing ->
              Just PreferenceCandidate
  where
    certificate = candidateCertificate candidate
    predicate = certificatePredicate certificate
