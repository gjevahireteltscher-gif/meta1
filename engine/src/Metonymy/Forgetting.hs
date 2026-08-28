module Metonymy.Forgetting
  ( inferForgetContext
  , safeToForget
  , rejectionCodes
  ) where

import Data.Char (isAlphaNum, toLower)
import Data.List (isInfixOf)
import Metonymy.Types

inferForgetContext :: String -> ForgetContext
inferForgetContext surface =
  ForgetContext
    { genericWholeFiber = not (hasAny namedOrTokenMarkers)
    , hasRestrictor = hasAny restrictorMarkers
    , hasQuantifier = hasAny quantifierMarkers
    , isPositive = not (hasAny negationMarkers)
    , isUnfocused = not (hasAny focusMarkers)
    , hasAnaphoricDependent = hasAny anaphoraMarkers
    , hasTemporalRestriction = hasAny temporalMarkers
    }
  where
    normalized = " " <> normalize surface <> " "
    hasAny = any (`isInfixOf` normalized)

safeToForget :: ForgetContext -> Bool
safeToForget context =
  genericWholeFiber context
    && not (hasRestrictor context)
    && not (hasQuantifier context)
    && isPositive context
    && isUnfocused context
    && not (hasAnaphoricDependent context)
    && not (hasTemporalRestriction context)

rejectionCodes :: ForgetContext -> [String]
rejectionCodes context =
  concat
    [ ["non-generic-fiber" | not (genericWholeFiber context)]
    , ["restrictive-modifier" | hasRestrictor context]
    , ["quantifier" | hasQuantifier context]
    , ["negation" | not (isPositive context)]
    , ["focus" | not (isUnfocused context)]
    , ["anaphoric-dependent" | hasAnaphoricDependent context]
    , ["temporal-restriction" | hasTemporalRestriction context]
    ]

normalize :: String -> String
normalize = map normalizeCharacter
  where
    normalizeCharacter character
      | isAlphaNum character = toLower character
      | otherwise = ' '

restrictorMarkers, quantifierMarkers, negationMarkers, focusMarkers, anaphoraMarkers, temporalMarkers, namedOrTokenMarkers :: [String]
restrictorMarkers = [" early works ", " selected works ", " first work ", " works from "]
quantifierMarkers = [" every ", " some ", " three ", " most ", " all but ", " only one "]
negationMarkers = [" not ", " never ", " no "]
focusMarkers = [" only ", " even ", " not "]
anaphoraMarkers = [" them ", " those works ", " it "]
temporalMarkers = [" yesterday ", " today ", " in 19", " from 19", " during "]
namedOrTokenMarkers = [" war and peace ", " masnavi ", " jaws ", " sandwich ", " orange juice ", " evening dress "]
